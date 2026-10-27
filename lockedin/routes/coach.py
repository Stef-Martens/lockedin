import json
import logging
import time
from collections.abc import Iterator
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import Connection, Engine, text

from lockedin.auth import require_owner
from lockedin.coach import usage
from lockedin.coach.llm import AnthropicLLM, CoachLLM
from lockedin.coach.loop import run_turn
from lockedin.coach.prompt import turn_context
from lockedin.coach.tools import GOAL_FIELDS, execute_tool
from lockedin.config import Settings, get_settings
from lockedin.db import get_conn, get_engine
from lockedin.routes.overview import get_now

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/coach", dependencies=[Depends(require_owner)])

TITLE_CHARS = 60
# The function may run 300 s (vercel.json maxDuration). The lock outlasts that, so a lock left behind by a
# killed function frees itself but never while an answer is still running; and no new tool round starts after
# ANSWER_BY_S, leaving the final no-tools answer a minute to finish.
TURN_LOCK = "6 minutes"
ANSWER_BY_S = 240
INTERRUPTED = "Interrupted before the tool finished."
SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


def get_llm(settings: Settings = Depends(get_settings)) -> CoachLLM:
    if not settings.anthropic_api_key:
        raise HTTPException(503, "The coach isn't set up yet: add ANTHROPIC_API_KEY in Vercel.")
    return AnthropicLLM(settings.anthropic_api_key, settings.anthropic_model)


def get_coach_engine() -> Engine:
    return get_engine()


class Message(BaseModel):
    text: str = Field(min_length=1, max_length=4000)

    @field_validator("text")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Type a message first.")
        return v.strip()


def _exists(conn: Connection, cid: int) -> None:
    if conn.execute(text("select 1 from coach_conversations where id = :c"), {"c": cid}).first() is None:
        raise HTTPException(404, "Conversation not found")


def _history(conn: Connection, cid: int) -> list[dict]:
    rows = conn.execute(text("select role, content from coach_messages where conversation_id = :c order by id"),
                        {"c": cid})
    history = [{"role": r.role, "content": r.content} for r in rows]
    # Every tool call must have a result before the next turn; answer one left unanswered by a crash.
    last = history[-1] if history else None
    if last and last["role"] == "assistant" and isinstance(last["content"], list):
        ids = [b["id"] for b in last["content"] if b.get("type") == "tool_use"]
        if ids:
            history.append({"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": i, "content": INTERRUPTED, "is_error": True} for i in ids]})
    return history


def display(history: list[dict]) -> list[dict]:
    """What the chat shows: the owner's messages, and each answer as one bubble with the tools it used."""
    out: list[dict] = []
    for m in history:
        if m["role"] == "user" and isinstance(m["content"], str):
            out.append({"role": "user", "text": m["content"], "tools": []})
        elif m["role"] == "assistant":
            if not out or out[-1]["role"] != "assistant":
                out.append({"role": "assistant", "text": "", "tools": []})
            bubble = out[-1]
            for block in m["content"]:
                if block.get("type") == "text" and block.get("text"):
                    bubble["text"] = f"{bubble['text']}\n\n{block['text']}" if bubble["text"] else block["text"]
                elif block.get("type") == "tool_use":
                    bubble["tools"].append(block["name"])
    return out


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


def over_budget(spent: float, budget: float) -> str:
    return (f"That's today's coach budget used up (about ${spent:.2f} of ${budget:.2f}). It resets at midnight; "
            "to allow more, raise COACH_DAILY_BUDGET_USD in Vercel.")


@router.get("/status")
def status(settings: Settings = Depends(get_settings), conn: Connection = Depends(get_conn),
           now: datetime = Depends(get_now)) -> dict:
    """Whether the coach can answer (an API key is set), so the page can say so before you type, and today's
    estimated spend against the daily budget."""
    return {"ready": bool(settings.anthropic_api_key), "model": settings.anthropic_model,
            "spent_today_usd": round(usage.spent_today(conn, now), 2),
            "daily_budget_usd": settings.coach_daily_budget_usd}


@router.get("/conversations")
def conversations(conn: Connection = Depends(get_conn)) -> list[dict]:
    # A chat whose first message failed has nothing to show, so it stays out of the list.
    rows = conn.execute(text(
        "select id, title, updated_at from coach_conversations c "
        "where exists (select 1 from coach_messages m where m.conversation_id = c.id) "
        "order by updated_at desc, id desc limit 50")).mappings()
    return [dict(r) for r in rows]


@router.post("/conversations", status_code=201)
def create_conversation(conn: Connection = Depends(get_conn), now: datetime = Depends(get_now),
                        _llm: CoachLLM = Depends(get_llm)) -> dict:
    """Refused with the setup message while there's no API key, so no empty chats pile up."""
    cid = conn.execute(text("insert into coach_conversations (created_at, updated_at) values (:n, :n) returning id"),
                       {"n": now}).scalar_one()
    return {"id": cid}


@router.get("/conversations/{cid}")
def conversation(cid: int, conn: Connection = Depends(get_conn)) -> dict:
    _exists(conn, cid)
    title = conn.execute(text("select title from coach_conversations where id = :c"), {"c": cid}).scalar()
    return {"id": cid, "title": title, "messages": display(_history(conn, cid))}


@router.post("/conversations/{cid}/messages")
def send_message(cid: int, body: Message, llm: CoachLLM = Depends(get_llm),
                 engine: Engine = Depends(get_coach_engine), now: datetime = Depends(get_now),
                 settings: Settings = Depends(get_settings)) -> StreamingResponse:
    deadline = time.monotonic() + ANSWER_BY_S
    with engine.begin() as conn:
        _exists(conn, cid)
        spent = usage.spent_today(conn, now)
        if spent >= settings.coach_daily_budget_usd:
            message = over_budget(spent, settings.coach_daily_budget_usd)
            return StreamingResponse(iter([_sse({"type": "error", "message": message})]),
                                     media_type="text/event-stream", headers=SSE_HEADERS)
        locked = conn.execute(text(
            "update coach_conversations set turn_started_at = now() where id = :c and "
            f"(turn_started_at is null or turn_started_at < now() - interval '{TURN_LOCK}') returning id"
        ), {"c": cid}).first()
        if locked is None:
            raise HTTPException(409, "The coach is still answering your last message in this chat. Give it a moment.")
        history = _history(conn, cid)
        context = turn_context(conn, now)

    # A round's tool calls and the transcript that records them commit in one transaction. If the function dies
    # in between, neither is kept: the chat never misses a change that was made, so a retry can't make it twice.
    round_conn: list[Connection] = []

    def round_tx() -> Connection:
        if not round_conn:
            conn = engine.connect()
            conn.begin()
            round_conn.append(conn)
        return round_conn[0]

    def end_round(commit: bool) -> None:
        if round_conn:
            conn = round_conn.pop()
            try:
                conn.commit() if commit else conn.rollback()
            finally:
                conn.close()

    def run_tool(name: str, args: object) -> tuple[str, bool]:
        conn = round_tx()
        with conn.begin_nested():  # a tool that crashes takes only its own changes with it
            return execute_tool(name, args, conn=conn, engine=engine, now=now)

    def save(messages: list[dict]) -> None:
        conn = round_tx()
        for message in messages:
            conn.execute(text("insert into coach_messages (conversation_id, role, content) "
                              "values (:c, :r, cast(:content as jsonb))"),
                         {"c": cid, "r": message["role"], "content": json.dumps(message["content"])})
        conn.execute(text("update coach_conversations set updated_at = now(), "
                          "title = coalesce(title, :title) where id = :c"),
                     {"c": cid, "title": body.text[:TITLE_CHARS] + ("…" if len(body.text) > TITLE_CHARS else "")})
        end_round(commit=True)

    def record_usage(calls: list[dict]) -> None:
        try:
            with engine.begin() as conn:
                usage.record(conn, cid, calls, now)
        except Exception:  # the answer matters more than the bookkeeping
            log.exception("couldn't record coach usage")

    def stream() -> Iterator[str]:
        try:
            for event in run_turn(llm, history=history, user_text=body.text, context=context, tool_runner=run_tool,
                                  deadline=deadline):
                if event["type"] == "appended":
                    save(event["messages"])
                elif event["type"] == "usage":
                    record_usage(event["usage"])
                else:
                    yield _sse(event)
        finally:
            end_round(commit=False)
            with engine.begin() as conn:
                conn.execute(text("update coach_conversations set turn_started_at = null where id = :c"), {"c": cid})

    return StreamingResponse(stream(), media_type="text/event-stream", headers=SSE_HEADERS)


@router.get("/goals")
def goals(conn: Connection = Depends(get_conn)) -> list[dict]:
    rows = conn.execute(text(f"select {GOAL_FIELDS} from goals "
                             "order by status <> 'active', updated_at desc, id desc")).mappings()
    return [dict(r) for r in rows]
