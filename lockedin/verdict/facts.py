"""What the model is told about a workout: the server's facts as JSON, never a raw chart series."""

from datetime import UTC, datetime

from fastapi.encoders import jsonable_encoder
from sqlalchemy import Connection

from lockedin.agenda import actual as act
from lockedin.agenda.blocks import blocks
from lockedin.agenda.detail import _easy_back, detail
from lockedin.focus.sessions import counted_sessions
from lockedin.focus.zones import hr_ranges
from lockedin.plan.goals import active_goals
from lockedin.routes.activities import gym_sets
from lockedin.timeutil import TZ
from lockedin.verdict.store import is_plan, ticking_item

COMPARISON = ("parts", "intervals_on_target", "splits", "zones", "rows")
RECENT = 3
EVER = datetime(2000, 1, 1, tzinfo=UTC)


def _plan(d: dict, zones: dict) -> dict:
    item, plan = d["item"], dict(d["plan"])
    if item["sport"] == "run" and zones:
        plan["zone_bpm"] = {str(z): list(bpm) for z, bpm in zones.items()}
        if plan.get("hr_bpm"):
            plan["hr_bpm"] = list(zones[plan["hr_zone"]])
    return {"title": item["title"], "note": item["note"], "optional": item["optional"], **plan}


def _planned_comparison(d: dict) -> dict:
    return {k: d["actual"][k] for k in COMPARISON if k in d["actual"]}


def _own_comparison(conn: Connection, a, s) -> dict:
    if a.sport == "run":
        return {"splits": act.splits(s, (None, None)), "zones": act.zones(conn, a.start_at, s)}
    if a.sport == "gym":
        return {"sets": gym_sets(conn, a.id)}
    return {}


def _recent(conn: Connection, a) -> list[dict]:
    earlier = [s for s in counted_sessions(conn, EVER, a.start_at, a.sport) if s.start_at < a.start_at]
    return [{"date": s.start_at.astimezone(TZ).date().isoformat(), "duration_s": s.duration_s,
             "distance_m": s.distance_m, "avg_hr": s.avg_hr, "avg_power": s.avg_power, "np": s.np,
             "avg_pace_s_per_km": s.avg_pace_s_per_km, "swim_pace_s_per_100m": s.swim_pace_s_per_100m}
            for s in reversed(earlier[-RECENT:])]


def facts(conn: Connection, now: datetime, activity_id: int) -> dict:
    a = act.activity(conn, activity_id)
    if a is None:
        raise LookupError(f"There's no activity {activity_id}.")
    item = ticking_item(conn, now, a)
    day = a.start_at.astimezone(TZ).date().isoformat()
    s = act.streams(conn, a.id, "t_offset, speed, hr, distance") if a.sport == "run" else None
    zones = hr_ranges(conn, a.start_at) if a.sport == "run" else {}

    plan = None
    if is_plan(item):
        d = detail(conn, now, item["id"])
        plan, comparison, easy_back = _plan(d, zones), _planned_comparison(d), d["easy_back"]
    else:
        comparison = _own_comparison(conn, a, s)
        easy_back = _easy_back(conn, {"sport": a.sport, "day": day})

    return jsonable_encoder({
        "workout": {**{k: v for k, v in a._mapping.items() if k not in ("id", "laps")}, "start_at": a.start_at.astimezone(TZ)},
        "plan": plan,
        "rest_day": item is not None and not is_plan(item),
        "comparison": comparison,
        "blocks": blocks(a.laps, (item["targets"] or {}).get("steps") if is_plan(item) else None, zones)
        if a.sport == "run" else None,
        "recent": _recent(conn, a),
        "easy_back": easy_back,
        "goals": [g["text"] for g in active_goals(conn)],
    })
