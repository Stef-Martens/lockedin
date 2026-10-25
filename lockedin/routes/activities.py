import math
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Connection, text

from lockedin.auth import require_owner
from lockedin.db import get_conn

router = APIRouter(prefix="/api/activities", dependencies=[Depends(require_owner)])

MAX_POINTS = 1200
STREAM_FIELDS = ("power", "hr", "cadence", "speed", "altitude", "distance")
SUMMARY_SQL = """
select a.id, a.source, a.sport, a.sub_type, a.start_at, a.end_at, a.duration_s, a.moving_s, a.distance_m,
       a.elevation_m, a.avg_hr, a.max_hr, a.avg_power, a.max_power, a.avg_cadence, a.np, a.if_, a.tss,
       a.avg_pace_s_per_km, a.swim_pace_s_per_100m, a.calories, a.superseded_by, a.hr_merged_from,
       g.title, (select count(*) from gym_sets s where s.workout_id = a.id) as set_count
from activities a left join gym_workouts g on g.activity_id = a.id
"""


def _summary(row) -> dict:
    d = dict(row._mapping)
    if d["set_count"] == 0 and d["sport"] != "gym":
        d["set_count"] = None
    return d


@router.get("")
def list_activities(
    sport: Literal["bike", "run", "swim", "gym", "other"] | None = None,
    include_walks: bool = False,
    include_superseded: bool = False,
    limit: int = Query(30, ge=1, le=200),
    before: datetime | None = None,
    conn: Connection = Depends(get_conn),
) -> dict:
    where, params = ["true"], {"limit": limit}
    if sport:
        where.append("a.sport = :sport"); params["sport"] = sport
    if not include_walks:
        where.append("coalesce(a.sub_type, '') not like 'walking%'")
    if not include_superseded:
        where.append("a.superseded_by is null")
    if before:
        where.append("a.start_at < :before"); params["before"] = before
    rows = conn.execute(text(f"{SUMMARY_SQL} where {' and '.join(where)} order by a.start_at desc limit :limit"), params).all()
    items = [_summary(r) for r in rows]
    return {"items": items, "next_before": items[-1]["start_at"] if len(items) == limit else None}


def downsample(streams: dict, max_points: int = MAX_POINTS) -> dict:
    """Bucket means so a long ride stays light for the phone; t_offset keeps each bucket's first value."""
    n = len(streams["t_offset"])
    size = max(1, math.ceil(n / max_points))
    out: dict = {"t_offset": streams["t_offset"][::size]}
    for f in STREAM_FIELDS:
        values = streams.get(f)
        if values is None:
            out[f] = None
            continue
        series = []
        for i in range(0, n, size):
            chunk = [v for v in values[i:i + size] if v is not None]
            series.append(round(sum(chunk) / len(chunk), 2) if chunk else None)
        out[f] = series if any(v is not None for v in series) else None
    return out


@router.get("/{activity_id}")
def get_activity(activity_id: int, conn: Connection = Depends(get_conn)) -> dict:
    row = conn.execute(text(f"{SUMMARY_SQL} where a.id = :i"), {"i": activity_id}).first()
    if not row:
        raise HTTPException(404, "Activity not found.")
    d = _summary(row)
    full = conn.execute(text("select * from activities where id = :i"), {"i": activity_id}).one()
    d |= {k: v for k, v in full._mapping.items() if k not in d}

    s = conn.execute(text("select * from activity_streams where activity_id = :i"), {"i": activity_id}).first()
    d["streams"] = downsample(dict(s._mapping)) if s and s.t_offset else None

    d["sets"] = [dict(r._mapping) for r in conn.execute(text(
        "select e.name as exercise, s.exercise_order, s.set_index, s.set_type, s.weight_kg, s.reps, s.rpe, "
        "s.e1rm, s.superset_id, s.notes, s.distance_km, s.duration_s from gym_sets s "
        "join exercises e on e.id = s.exercise_id where s.workout_id = :i order by s.exercise_order, s.set_index"
    ), {"i": activity_id})] if d["sport"] == "gym" else None

    for key in ("superseded_by", "hr_merged_from"):
        ref = d[key]
        other = conn.execute(text(f"{SUMMARY_SQL} where a.id = :i"), {"i": ref}).first() if ref else None
        d[f"{key}_summary"] = _summary(other) if other else None
    return d
