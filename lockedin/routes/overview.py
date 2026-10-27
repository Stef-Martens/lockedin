from datetime import UTC, date, datetime, timedelta
from itertools import zip_longest

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import Connection, text

from lockedin.auth import require_owner
from lockedin.db import get_conn
from lockedin.focus.consistency import comeback, totals, week_streak, weekly_volume
from lockedin.focus.facts import focus_facts
from lockedin.focus.mix import session_suggestions
from lockedin.focus.suggest import gym_suggestions
from lockedin.focus.wins import plateaus, recent_wins
from lockedin.reminders import checkin_due, hevy_due, next_checkin_due
from lockedin.timeoff import _fmt, away_on, describe, entries, entry_on, off_on
from lockedin.timeutil import TZ

router = APIRouter(prefix="/api", dependencies=[Depends(require_owner)])

FOCUS_ITEMS = 3
BACK_FROM_DAYS = 14


def _time_off_today(conn: Connection, today: date) -> str | None:
    off = off_on(conn, today)
    if "all" in off:
        entry = entry_on(conn, today)
        return f"{'Vacation' if entry and entry['reason'] == 'vacation' else 'Everything off'} until {_fmt(off['all'])}"
    return describe(off) if off else None


def _back_from_card(conn: Connection, today: date) -> dict | None:
    """The injury with a restriction that ended in the last BACK_FROM_DAYS days (latest-ending), unless it is off again."""
    off = off_on(conn, today)
    lo = today - timedelta(days=BACK_FROM_DAYS)
    hits = [(r["until"], e["id"], e) for e in entries(conn, lo) if e["reason"] == "injury"
            for r in e["restrictions"] if lo <= r["until"] < today and r["category"] not in off]
    if not hits:
        return None
    e = max(hits, key=lambda h: h[:2])[2]
    return {"title": f"Back from: {e['label']}" if e["label"] else "Back from your operation", "label": e["label"]}


def get_now() -> datetime:
    return datetime.now(UTC)


@router.get("/overview")
def overview(weeks: int = 12, conn: Connection = Depends(get_conn), now: datetime = Depends(get_now)) -> dict:
    if weeks not in (12, 26):
        raise HTTPException(422, "weeks must be 12 or 26")
    back = comeback(conn, now)
    if back:
        # After a break the one easy restart suggestion stands alone; deficits caused by the break would contradict it.
        focus = []
    else:
        gym = [{"type": "gym", **jsonable_encoder(g)} for g in gym_suggestions(conn, now)]
        sessions = [{"type": "session", **jsonable_encoder(s)} for s in session_suggestions(conn, now)]
        mixed = [x for pair in zip_longest(gym, sessions) for x in pair if x]
        focus = sorted(mixed, key=lambda x: x.get("goal") is None)[:FOCUS_ITEMS]  # goal items first
    last_tape = conn.execute(text(
        "select max(m.measured_on) from measurements m join measurement_types t on t.id = m.type_id where t.kind = 'tape'"
    )).scalar()
    today = now.astimezone(TZ).date()
    due = checkin_due(conn, today)
    hevy_is_due, hevy_last = hevy_due(conn, now)
    return jsonable_encoder({
        "totals": totals(conn, now),
        "weekly": weekly_volume(conn, now, weeks),
        "streak": week_streak(conn, now),
        "comeback": back,
        "time_off_today": _time_off_today(conn, today),
        "back_from": _back_from_card(conn, today),
        "wins": recent_wins(conn, now),
        "plateaus": [] if back or away_on(conn, today) else plateaus(conn, now),
        "focus": focus,
        "measure_due": due,
        "checkin_due": due,
        "next_checkin_on": next_checkin_due(conn, today),
        "last_checkin_on": conn.execute(text("select max(measured_on) from measurements")).scalar(),
        "hevy_due": hevy_is_due,
        "hevy_last_upload_at": hevy_last,
        "last_tape_measurement_on": last_tape,
    })


@router.get("/focus")
def focus(conn: Connection = Depends(get_conn), now: datetime = Depends(get_now)) -> dict:
    return focus_facts(conn, now)
