"""Saved verdicts on workouts: finding the workout and its plan, and the claim that keeps the model call to one."""

from datetime import datetime, timedelta

from sqlalchemy import Connection, Row, text

from lockedin.agenda.store import items_between
from lockedin.focus.sessions import COUNTED_SQL
from lockedin.timeutil import TZ

CLAIM_TTL = timedelta(minutes=6)
FAIL_WAIT = timedelta(minutes=15)

_ACTIVITY = f"select id, sport, sub_type, start_at, duration_s from activities where {COUNTED_SQL}"


def latest_activity(conn: Connection, now: datetime) -> Row | None:
    return conn.execute(text(f"{_ACTIVITY} and start_at <= :now order by start_at desc limit 1"), {"now": now}).first()


def counted_activity(conn: Connection, activity_id: int) -> Row | None:
    return conn.execute(text(f"{_ACTIVITY} and id = :i"), {"i": activity_id}).first()


def ticking_item(conn: Connection, now: datetime, activity) -> dict | None:
    """The agenda item this workout ticks off, found over its local day."""
    day = activity.start_at.astimezone(TZ).date()
    return next((i for i in items_between(conn, now, day, day) if i["activity_id"] == activity.id), None)


def is_plan(item: dict | None) -> bool:
    """A rest day isn't a plan for a workout."""
    return item is not None and item["sport"] != "rest"


def read(conn: Connection, activity_id: int) -> Row | None:
    return conn.execute(text("select * from workout_verdicts where activity_id = :i"), {"i": activity_id}).first()


def up_to_date(row, item: dict | None) -> bool:
    """False when the plan appeared or went away since it was written; a different item doesn't count."""
    if row.label == "unplanned":
        return not is_plan(item)
    return is_plan(item)


def claim(conn: Connection, activity_id: int, item_id: int | None, now: datetime, rewrite: bool = False) -> bool:
    """True when this caller may call the model. One statement, so two callers can't both win."""
    return conn.execute(text(
        "insert into workout_verdicts (activity_id, item_id, claimed_at) values (:a, :item, :now) "
        "on conflict (activity_id) do update set item_id = excluded.item_id, claimed_at = excluded.claimed_at "
        "where (workout_verdicts.written_at is null or :rewrite) "
        "and (workout_verdicts.claimed_at is null or workout_verdicts.claimed_at < :now - :ttl) "
        "and (workout_verdicts.failed_at is null or workout_verdicts.failed_at < :now - :wait) "
        "returning 1"
    ), {"a": activity_id, "item": item_id, "now": now, "rewrite": rewrite, "ttl": CLAIM_TTL, "wait": FAIL_WAIT}).first() is not None


def save(conn: Connection, activity_id: int, label: str, body: str, model: str, now: datetime) -> None:
    conn.execute(text(
        "update workout_verdicts set label = :l, body = :b, model = :m, written_at = :now, failed_at = null, "
        "claimed_at = null where activity_id = :a"
    ), {"a": activity_id, "l": label, "b": body, "m": model, "now": now})


def fail(conn: Connection, activity_id: int, now: datetime) -> None:
    conn.execute(text("update workout_verdicts set failed_at = :now, claimed_at = null where activity_id = :a"),
                 {"a": activity_id, "now": now})
