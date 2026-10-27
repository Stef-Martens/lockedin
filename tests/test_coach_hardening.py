import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import anthropic
import httpx2
import pytest
from conftest import ROOT, owner_headers
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool
from test_coach_loop import FakeLLM, answer, go, runner, tool_use, tools_turn
from test_routes_coach import events, fake, new_conversation, send  # noqa: F401 (fixture)

from lockedin.app import app
from lockedin.coach import usage
from lockedin.coach.llm import TOO_LONG, AnthropicLLM, CoachUnavailable, Final, usage_of
from lockedin.coach.loop import OUT_OF_TIME
from lockedin.coach.sql import QueryRejected, run_readonly
from lockedin.config import get_settings
from lockedin.routes import coach

MILLION = 1_000_000


def call(model="claude-opus-5-5", i=0, o=0, r=0, w=0):
    return {"model": model, "input_tokens": i, "output_tokens": o, "cache_read_tokens": r, "cache_write_tokens": w}


# --- pricing and usage -------------------------------------------------------------------------------------------

def test_opus_5_5_prices():
    assert usage.cost(call(i=MILLION)) == pytest.approx(4.00)
    assert usage.cost(call(o=MILLION)) == pytest.approx(20.00)
    assert usage.cost(call(r=MILLION)) == pytest.approx(0.20)
    assert usage.cost(call(w=MILLION)) == pytest.approx(5.00)  # 5-minute cache write: 1.25x input


def test_fallback_and_unknown_models_are_priced():
    assert usage.cost(call("claude-opus-4-8", i=MILLION, r=MILLION)) == pytest.approx(5.50)
    assert usage.price("claude-opus-5") == (5.00, 25.00, 0.50)
    assert usage.price("claude-opus-5-5") == (4.00, 20.00, 0.20)
    assert usage.price("claude-something-new") == usage.UNKNOWN_PRICE


def ns(**kw):
    return SimpleNamespace(**kw)


def tokens(**kw):
    base = {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}
    return {**base, **kw}


def test_usage_counts_every_fallback_attempt():
    declined = ns(type="message", model=None, **tokens(input_tokens=100, output_tokens=5))
    served = ns(type="fallback_message", model="claude-opus-4-8", **tokens(input_tokens=90, output_tokens=50,
                                                                          cache_read_input_tokens=1000))
    message = ns(model="claude-opus-4-8", usage=ns(iterations=[declined, served], **tokens(input_tokens=90)))
    assert usage_of(message, "claude-opus-5-5") == [
        call("claude-opus-5-5", i=100, o=5), call("claude-opus-4-8", i=90, o=50, r=1000)]


def test_usage_without_iterations_uses_the_top_level_numbers():
    message = ns(model="claude-opus-5-5", usage=ns(iterations=None, **tokens(input_tokens=10, output_tokens=20,
                                                                           cache_creation_input_tokens=30)))
    assert usage_of(message, "claude-opus-5-5") == [call(i=10, o=20, w=30)]


# --- the API client: usage and structured errors -------------------------------------------------------------------

class FakeStream:
    def __init__(self, final):
        self.final = final

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def __iter__(self):
        return iter([])

    def get_final_message(self):
        return self.final


def llm_with(stream) -> AnthropicLLM:
    llm = AnthropicLLM.__new__(AnthropicLLM)
    llm._anthropic, llm.model = anthropic, "claude-opus-5-5"
    llm.client = ns(beta=ns(messages=ns(stream=stream)))
    return llm


def test_api_final_message_carries_usage():
    final = ns(model="claude-opus-5-5", stop_reason="end_turn",
               usage=ns(iterations=None, **tokens(input_tokens=7, output_tokens=3)),
               to_dict=lambda mode: {"content": [{"type": "text", "text": "hi"}]})
    out = list(llm_with(lambda **kw: FakeStream(final)).stream(system="s", messages=[], tools=[]))
    assert out == [Final(content=[{"type": "text", "text": "hi"}], stop_reason="end_turn", usage=[call(i=7, o=3)])]


def api_error(cls, status: int, message: str):
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    body = {"type": "error", "error": {"type": "invalid_request_error", "message": message}}
    return cls(f"Error code: {status} - {json.dumps(body)}", response=httpx2.Response(status, request=request, json=body),
               body=body)


@pytest.mark.parametrize("error, shown", [
    (api_error(anthropic.BadRequestError, 400, "prompt is too long: 1000123 tokens > 1000000 maximum"), TOO_LONG),
    (api_error(anthropic.RequestTooLargeError, 413, "Request exceeds the maximum size"), TOO_LONG),
    # Mentions "context" but isn't about length.
    (api_error(anthropic.BadRequestError, 400, "context_management: Extra inputs are not permitted"),
     "The coach request was rejected; try starting a new conversation."),
])
def test_too_long_is_read_from_the_error_itself(error, shown):
    def stream(**kw):
        raise error
    with pytest.raises(CoachUnavailable) as e:
        list(llm_with(stream).stream(system="s", messages=[], tools=[]))
    assert str(e.value) == shown


# --- the loop: time limit, usage events -----------------------------------------------------------------------------

class Recording(FakeLLM):
    def stream(self, *, system, messages, tools, tool_choice=None):
        self.choices = [*getattr(self, "choices", []), tool_choice]
        yield from super().stream(system=system, messages=messages, tools=tools)


def test_no_new_tool_round_after_the_deadline():
    llm = Recording([tools_turn(tool_use(1, "get_goals")), answer("Here's what I have.")])
    clock = iter([100.0, 100.0, 100.0])
    history, evs = go(llm, deadline=50.0, clock=lambda: next(clock))
    assert llm.choices == [None, {"type": "none"}]
    assert llm.calls[-1]["messages"][-1] == {"role": "system", "content": OUT_OF_TIME}
    assert evs[-1] == {"type": "done"} and history[-2] == {"role": "system", "content": OUT_OF_TIME}


def test_before_the_deadline_tools_keep_going():
    llm = Recording([tools_turn(tool_use(1, "get_goals")), tools_turn(tool_use(2, "get_goals")), answer("ok")])
    run = runner()
    go(llm, tool_runner=run, deadline=50.0, clock=lambda: 10.0)
    assert llm.choices == [None, None, None] and len(run.calls) == 2


class Billed(FakeLLM):
    """Each scripted turn also reports one call's usage."""

    def __init__(self, turns, per_call):
        super().__init__(turns)
        self.per_call = per_call

    def stream(self, *, system, messages, tools, tool_choice=None):
        for item in super().stream(system=system, messages=messages, tools=tools):
            yield Final(item.content, item.stop_reason, [self.per_call]) if isinstance(item, Final) else item


def test_loop_reports_usage_and_stops_when_the_context_is_full():
    llm = Billed([([], [{"type": "text", "text": "par"}], "model_context_window_exceeded")], call(i=5))
    history, evs = go(llm)
    assert {"type": "usage", "usage": [call(i=5)]} in evs
    assert evs[-1] == {"type": "error", "message": TOO_LONG} and history == []


# --- the route: spend recorded, budget enforced, rounds atomic --------------------------------------------------

@pytest.fixture
def billed(client, clean_db, fake):
    llm = Billed([], call(i=MILLION, o=50_000))  # $4 + $1 = $5 per call
    app.dependency_overrides[coach.get_llm] = lambda: llm
    return llm


def test_each_call_is_recorded_and_today_is_shown(client, billed, clean_db):
    billed.turns = [tools_turn(tool_use(1, "get_goals")), answer("Done.")]
    cid = new_conversation(client)
    assert events(send(client, cid))[-1] == {"type": "done"}
    with clean_db.begin() as c:
        rows = c.execute(text("select conversation_id, model, input_tokens, output_tokens, cost_usd from coach.usage "
                              "order by id")).all()
    assert [(r.conversation_id, r.model, r.input_tokens, r.output_tokens, float(r.cost_usd)) for r in rows] == \
        [(cid, "claude-opus-5-5", MILLION, 50_000, 5.0)] * 2
    status = client.get("/api/coach/status", headers=owner_headers()).json()
    assert status["spent_today_usd"] == 10.0 and status["daily_budget_usd"] == 5.0


def add_spend(clean_db, usd: float, at: datetime) -> None:
    with clean_db.begin() as c:
        c.execute(text("insert into coach.usage (model, cost_usd, created_at) values ('claude-opus-5-5', :u, :t)"),
                  {"u": usd, "t": at})


def test_over_budget_answers_plainly_without_calling_claude(client, fake, clean_db):
    fake.turns = [answer("should not happen")]
    add_spend(clean_db, 5.0, datetime.now(UTC))
    cid = new_conversation(client)
    r = send(client, cid)
    assert r.status_code == 200
    assert events(r) == [{"type": "error", "message": coach.over_budget(5.0, 5.0)}]
    assert "resets at midnight" in events(r)[0]["message"] and fake.calls == []
    with clean_db.begin() as c:
        assert c.execute(text("select turn_started_at from coach_conversations where id = :c"), {"c": cid}).scalar() is None


def test_yesterdays_spend_doesnt_count(client, fake, clean_db):
    fake.turns = [answer("ok")]
    add_spend(clean_db, 50.0, datetime.now(UTC) - timedelta(days=2))
    assert events(send(client, new_conversation(client)))[-1] == {"type": "done"}


class Killed(BaseException):
    """The function being stopped mid-round (Vercel's time limit, a deploy)."""


def test_a_round_cut_short_keeps_neither_the_change_nor_the_transcript(clean_db, monkeypatch):
    real = coach.execute_tool

    def dies_on_second_tool(name, args, **kw):
        if name == "get_goals":
            raise Killed
        return real(name, args, **kw)

    monkeypatch.setattr(coach, "execute_tool", dies_on_second_tool)
    monkeypatch.setattr(coach, "StreamingResponse", lambda content, **kw: content)  # drive the stream directly
    llm = FakeLLM([tools_turn(tool_use(1, "save_agenda", {"changes": [
        {"op": "add", "day": "2026-10-30", "sport": "rest", "title": "Rest day"}]}), tool_use(2, "get_goals"))])
    with clean_db.begin() as c:
        cid = c.execute(text("insert into coach_conversations default values returning id")).scalar_one()
    stream = coach.send_message(cid, coach.Message(text="Plan a rest day"), llm=llm, engine=clean_db,
                                now=datetime.now(UTC), settings=get_settings())
    with pytest.raises(Killed):
        list(stream)
    with clean_db.begin() as c:
        assert c.execute(text("select count(*) from agenda_items")).scalar() == 0
        assert c.execute(text("select count(*) from coach_messages")).scalar() == 0
        assert c.execute(text("select turn_started_at from coach_conversations where id = :c"), {"c": cid}).scalar() is None


def test_a_finished_round_keeps_change_and_transcript_together(client, fake, clean_db):
    fake.turns = [tools_turn(tool_use(1, "save_agenda", {"changes": [
        {"op": "add", "day": "2026-10-30", "sport": "rest", "title": "Rest day"}]})), answer("Added.")]
    assert events(send(client, new_conversation(client)))[-1] == {"type": "done"}
    with clean_db.begin() as c:
        assert c.execute(text("select count(*) from agenda_items")).scalar() == 1
        assert c.execute(text("select count(*) from coach_messages where role = 'assistant'")).scalar() == 2


def test_turn_lock_outlasts_the_function_and_answers_start_before_it_ends():
    max_duration = json.loads((ROOT / "vercel.json").read_text())["services"]["api"]["functions"]["lockedin/app.py"][
        "maxDuration"]
    minutes = int(coach.TURN_LOCK.split()[0])
    assert minutes * 60 > max_duration and coach.ANSWER_BY_S <= max_duration - 60


# --- SQL tool limits, schema ------------------------------------------------------------------------------------

@pytest.fixture
def one_connection(clean_db):
    """One long-lived session, like a pooler's: what a query leaves behind stays visible."""
    eng = create_engine(clean_db.url, poolclass=StaticPool, connect_args={"prepare_threshold": None})
    yield eng
    eng.dispose()


def held_advisory_locks(eng) -> int:
    with eng.connect() as c:
        return c.execute(text("select count(*) from pg_locks where locktype = 'advisory' "
                              "and pid = pg_backend_pid()")).scalar()


def test_advisory_locks_are_released_when_the_query_fails(one_connection):
    with pytest.raises(QueryRejected, match="division by zero"):
        run_readonly(one_connection, "with l as materialized (select pg_advisory_lock(42)) "
                                     "select 1 / (select count(*)::int - 1 from l)")
    assert held_advisory_locks(one_connection) == 0


def test_advisory_locks_are_released_after_success(one_connection):
    run_readonly(one_connection, "select pg_advisory_lock(42)")
    assert held_advisory_locks(one_connection) == 0


def test_queries_get_little_sort_memory(clean_db):
    assert run_readonly(clean_db, "select current_setting('work_mem') as w")["rows"] == [["2MB"]]


def test_usage_is_private_and_gym_sets_are_indexed_by_workout(conn):
    for role in ("anon", "authenticated", "coach_ro"):
        assert not conn.execute(text("select has_table_privilege(:r, 'coach.usage', 'select')"), {"r": role}).scalar()
    defs = conn.execute(text("select indexdef from pg_indexes where tablename = 'gym_sets'")).scalars().all()
    assert any("(workout_id" in d for d in defs)
