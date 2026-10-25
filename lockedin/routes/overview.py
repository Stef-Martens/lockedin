from datetime import UTC, datetime
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
from lockedin.timeutil import TZ

router = APIRouter(prefix="/api", dependencies=[Depends(require_owner)])

FOCUS_ITEMS = 3


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
        focus = [x for pair in zip_longest(gym, sessions) for x in pair if x][:FOCUS_ITEMS]
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
        "wins": recent_wins(conn, now),
        "plateaus": [] if back else plateaus(conn, now),
        "focus": focus,
        "measure_due": due,
        "checkin_due": due,
        "next_checkin_on": next_checkin_due(conn, today),
        "hevy_due": hevy_is_due,
        "hevy_last_upload_at": hevy_last,
        "last_tape_measurement_on": last_tape,
    })


@router.get("/focus")
def focus(conn: Connection = Depends(get_conn), now: datetime = Depends(get_now)) -> dict:
    return focus_facts(conn, now)
