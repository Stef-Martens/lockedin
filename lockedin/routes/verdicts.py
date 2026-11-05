import logging
from collections.abc import Callable
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import Engine

from lockedin.auth import require_owner
from lockedin.coach import usage
from lockedin.coach.llm import AnthropicLLM, CoachLLM
from lockedin.config import Settings, get_settings
from lockedin.routes.coach import get_coach_engine
from lockedin.routes.overview import get_now
from lockedin.verdict import store
from lockedin.verdict.facts import facts as build_facts
from lockedin.verdict.store import NEW_FOR
from lockedin.verdict.write import VerdictFailed, write

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/verdicts", dependencies=[Depends(require_owner)])


def get_verdict_llm(settings: Settings = Depends(get_settings)) -> Callable[[], CoachLLM] | None:
    """None without an API key (unlike the coach, a missing key isn't an error here); otherwise a factory, so
    the SDK is only loaded once a verdict is really being written."""
    if not settings.anthropic_api_key:
        return None
    return lambda: AnthropicLLM(settings.anthropic_api_key, settings.anthropic_model)


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


def _record(engine: Engine, calls: list[dict], now: datetime) -> None:
    try:
        with engine.begin() as conn:
            usage.record(conn, None, calls, now)
    except Exception:  # the verdict matters more than the bookkeeping
        log.exception("couldn't record verdict usage")


def _fail(engine: Engine, activity_id: int, now: datetime) -> dict:
    try:
        with engine.begin() as conn:
            store.fail(conn, activity_id, now)
    except Exception:
        log.exception("couldn't mark verdict %s failed", activity_id)
    return {"status": "failed"}


def _written(row) -> bool:
    return row is not None and row.written_at is not None


def _done(row) -> dict:
    return {"status": "done", "label": row.label, "text": row.body}


def _decide(engine: Engine, settings: Settings, make_llm: Callable[[], CoachLLM] | None, now: datetime, a, item: dict | None,
            old: bool) -> dict:
    with engine.begin() as conn:
        row = store.read(conn, a.id)
        written = _written(row)
        current = written and store.up_to_date(row, item)
        if current or (written and old):
            return _done(row)
        if old or make_llm is None:
            return {"status": "none"}
        spent = usage.spent_today(conn, now)
        if spent >= settings.coach_daily_budget_usd:
            return {"status": "over_budget"}
        if not store.claim(conn, a.id, item["id"] if item else None, now, rewrite=written):
            row = store.read(conn, a.id)
            if _written(row) and store.up_to_date(row, item):
                return _done(row)
            failed = row is not None and row.failed_at is not None and now - row.failed_at < store.FAIL_WAIT
            return {"status": "failed" if failed else "writing"}

    try:
        with engine.begin() as conn:
            f = build_facts(conn, now, a.id)
        written_verdict = write(make_llm(), f, store.is_plan(item))
    except VerdictFailed as e:
        log.warning("verdict %s failed: %s", a.id, e)
        _record(engine, e.usage, now)
        return _fail(engine, a.id, now)
    except Exception:
        log.exception("verdict %s failed", a.id)
        return _fail(engine, a.id, now)

    try:
        with engine.begin() as conn:
            store.save(conn, a.id, written_verdict.label, written_verdict.text, settings.anthropic_model, now)
    except Exception:
        log.exception("couldn't save verdict %s", a.id)
        _record(engine, written_verdict.usage, now)
        return _fail(engine, a.id, now)
    _record(engine, written_verdict.usage, now)
    return {"status": "done", "label": written_verdict.label, "text": written_verdict.text}


def _respond(engine: Engine, settings: Settings, make_llm: Callable[[], CoachLLM] | None, now: datetime, a, old: bool) -> dict:
    with engine.begin() as conn:
        item = store.ticking_item(conn, now, a)
    verdict = _decide(engine, settings, make_llm, now, a, item, old)
    return {"activity": {"id": a.id, "sport": a.sport, "day": a.start_at.astimezone(store.TZ).date().isoformat(),
                         "start_at": a.start_at, "title": item["title"] if item else None,
                         "item_id": item["id"] if item else None},
            "verdict": verdict}


@router.get("/latest", dependencies=[Depends(_no_store)])
def latest(engine: Engine = Depends(get_coach_engine), now: datetime = Depends(get_now),
           settings: Settings = Depends(get_settings), make_llm: Callable[[], CoachLLM] | None = Depends(get_verdict_llm)) -> dict:
    with engine.begin() as conn:
        a = store.latest_activity(conn, now)
    if a is None or now - a.start_at > NEW_FOR:
        return {"activity": None}
    return _respond(engine, settings, make_llm, now, a, old=False)


@router.get("/{activity_id}", dependencies=[Depends(_no_store)])
def one(activity_id: int, engine: Engine = Depends(get_coach_engine), now: datetime = Depends(get_now),
        settings: Settings = Depends(get_settings), make_llm: Callable[[], CoachLLM] | None = Depends(get_verdict_llm)) -> dict:
    with engine.begin() as conn:
        a = store.counted_activity(conn, activity_id)
    if a is None:
        raise HTTPException(404, "Workout not found")
    return _respond(engine, settings, make_llm, now, a, old=now - a.start_at > NEW_FOR)
