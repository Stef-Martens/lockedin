import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import Connection, text

from lockedin.auth import require_owner
from lockedin.db import get_conn
from lockedin.focus.consistency import in_comeback
from lockedin.focus.preferences import load_preferences, prefs_hash
from lockedin.plan.build import NoRoutine, build_plan, swap_item
from lockedin.goals.progress import progress
from lockedin.plan.goals import active_goals
from lockedin.plan.routines import routine, routines
from lockedin.routes.overview import get_now
from lockedin.timeutil import TZ

router = APIRouter(prefix="/api", dependencies=[Depends(require_owner)])
MAX_NEVER = 200


def _built_in_comeback(row) -> bool:
    return any(i.get("change") == "welcome_back" for i in row.items)


def _out(row, conn: Connection, now: datetime) -> dict:
    # What the plan was built for, so the banner always matches the targets shown.
    back = _built_in_comeback(row) if row.day else in_comeback(conn, now)
    return {"id": row.id, "day": row.day, "built_on": row.built_on.isoformat(), "comeback": back, "items": row.items}


def _store(conn: Connection, plan: dict):
    return conn.execute(text(
        "insert into workout_plans (day, built_on, source_activity_id, prefs_hash, items) "
        "values (:day, :built_on, :src, :hash, cast(:items as jsonb)) returning *"
    ), {"day": plan["day"], "built_on": plan["built_on"], "src": plan["source_activity_id"],
        "hash": plan["prefs_hash"], "items": json.dumps(plan["items"])}).one()


def _build(conn: Connection, now: datetime, day: str | None):
    try:
        return _store(conn, build_plan(conn, now, day))
    except NoRoutine as e:
        raise HTTPException(404, str(e)) from None
    except ValueError as e:
        raise HTTPException(409, str(e)) from None


def _is_fresh(conn: Connection, now: datetime, row) -> bool:
    """Same local day, same latest workout for the routine, same preferences."""
    if row.built_on != now.astimezone(TZ).date() or row.prefs_hash != prefs_hash(load_preferences(conn)):
        return False
    if row.day is None:
        return True
    current = routine(conn, now, row.day)
    if current is None or current.activity_id != row.source_activity_id:
        return False
    # A break starting (or ending) during the day changes the targets.
    return _built_in_comeback(row) == in_comeback(conn, now) or not any(i["kind"] == "routine" for i in row.items)


@router.get("/plan/days")
def plan_days(conn: Connection = Depends(get_conn), now: datetime = Depends(get_now)) -> dict:
    back = in_comeback(conn, now)
    return jsonable_encoder({
        "days": [{"title": r.title, "last_done": r.last_done.astimezone(TZ).date(), "exercise_count": len(r.exercises)}
                 for r in routines(conn, now)],
        "missed_available": not back,
        "comeback": back,
        "goals": [{"id": g["id"], "text": g["text"], "target": g["target"]} for g in active_goals(conn)],
    })


@router.get("/plan")
def get_plan(day: str | None = None, conn: Connection = Depends(get_conn), now: datetime = Depends(get_now)) -> dict:
    row = conn.execute(text(
        "select * from workout_plans where day is not distinct from :day order by id desc limit 1"
    ), {"day": day}).first()
    if row is None or not _is_fresh(conn, now, row):
        row = _build(conn, now, day)
    return _out(row, conn, now)


@router.post("/plan/new")
def new_plan(day: str | None = None, conn: Connection = Depends(get_conn), now: datetime = Depends(get_now)) -> dict:
    return _out(_build(conn, now, day), conn, now)


def _locked(conn: Connection, plan_id: int, item_id: str):
    row = conn.execute(text("select * from workout_plans where id = :i for update"), {"i": plan_id}).first()
    if row is None or not any(it["id"] == item_id for it in row.items):
        raise HTTPException(404, "That plan item no longer exists.")
    return row


def _save_items(conn: Connection, plan_id: int, items: list, refresh_hash: bool = False):
    sets = ", prefs_hash = :hash" if refresh_hash else ""
    return conn.execute(text(
        f"update workout_plans set items = cast(:items as jsonb), updated_at = now(){sets} where id = :i returning *"
    ), {"items": json.dumps(items), "i": plan_id, "hash": prefs_hash(load_preferences(conn))}).one()


def _swapped(conn: Connection, now: datetime, row, item_id: str) -> list:
    try:
        return swap_item(conn, now, {"day": row.day, "items": row.items}, item_id)["items"]
    except LookupError as e:
        raise HTTPException(409, str(e)) from None


@router.post("/plan/{plan_id}/items/{item_id}/swap")
def swap(plan_id: int, item_id: str, conn: Connection = Depends(get_conn), now: datetime = Depends(get_now)) -> dict:
    row = _locked(conn, plan_id, item_id)
    return _out(_save_items(conn, plan_id, _swapped(conn, now, row, item_id)), conn, now)


@router.post("/plan/{plan_id}/items/{item_id}/skip")
def skip(plan_id: int, item_id: str, conn: Connection = Depends(get_conn), now: datetime = Depends(get_now)) -> dict:
    row = _locked(conn, plan_id, item_id)
    items = [{**it, "skipped": not it["skipped"]} if it["id"] == item_id else it for it in row.items]
    return _out(_save_items(conn, plan_id, items), conn, now)


@router.post("/plan/{plan_id}/items/{item_id}/never")
def never(plan_id: int, item_id: str, conn: Connection = Depends(get_conn), now: datetime = Depends(get_now)) -> dict:
    row = _locked(conn, plan_id, item_id)
    item = next(it for it in row.items if it["id"] == item_id)
    if not item["suggested"]:
        raise HTTPException(400, "This one is from your own routine; use Swap or Skip instead.")
    was_current = row.prefs_hash == prefs_hash(load_preferences(conn))
    never = [n for n in load_preferences(conn).never_exercises if n != item["exercise"]] + [item["exercise"]]
    conn.execute(text("update profile set never_exercises = :n, updated_at = now() where id = 1"),
                 {"n": never[-MAX_NEVER:]})  # keep the latest 200
    if not was_current:  # the plan was already out of date: build a fresh one with every preference applied
        return _out(_build(conn, now, row.day), conn, now)
    try:
        items = swap_item(conn, now, {"day": row.day, "items": row.items}, item_id)["items"]
    except LookupError:
        items = [it for it in row.items if it["id"] != item_id]  # nothing else for that muscle: drop the extra
    # The plan now reflects the new preference, so keep it current instead of rebuilding it on the next open.
    return _out(_save_items(conn, plan_id, items, refresh_hash=True), conn, now)


@router.get("/goals/active")
def goals_active(conn: Connection = Depends(get_conn), now: datetime = Depends(get_now)) -> list[dict]:
    return jsonable_encoder([{"id": g["id"], "text": g["text"], "target": g["target"], "area": g["area"],
                              "exercise": g["exercise"], "progress": progress(conn, now, g)} for g in active_goals(conn)])
