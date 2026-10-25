"""Weekly working sets per muscle (primary set = 1, secondary = ½; warm-ups don't count)."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from sqlalchemy import Connection, text

from lockedin.focus.sessions import COUNTED_SQL, counted

HIGH_FACTOR = 1.5


@dataclass
class MuscleCoverage:
    key: str
    name: str
    region: str
    sets_per_week: float
    target_low: float
    target_high: float
    status: Literal["low", "ok", "high"]


def _gym_window(days: int, now: datetime) -> dict:
    return {"since": now - timedelta(days=days), "now": now}


def muscle_coverage(conn: Connection, now: datetime, days: int = 28) -> list[MuscleCoverage]:
    params = _gym_window(days, now)
    trained = conn.execute(text(
        f"select 1 from activities where sport = 'gym' and {COUNTED_SQL} and start_at > :since and start_at <= :now limit 1"
    ), params).first()
    if not trained:
        return []
    credit = dict(conn.execute(text(
        "select lm.muscle_key, sum(case lm.role when 'primary' then 1.0 else 0.5 end) "
        "from gym_sets s join activities a on a.id = s.workout_id join exercises e on e.id = s.exercise_id "
        "join library_muscles lm on lm.exercise_name = e.name "
        f"where {counted('a')} and a.start_at > :since and a.start_at <= :now "
        "and s.set_type <> 'warmup' group by lm.muscle_key"
    ), params).all())
    weeks = days / 7
    out = []
    for m in conn.execute(text("select * from muscles order by sort")):
        per_week = round(float(credit.get(m.key, 0)) / weeks, 2)
        status = "low" if per_week < m.target_low else "high" if per_week > m.target_high * HIGH_FACTOR else "ok"
        out.append(MuscleCoverage(m.key, m.name, m.region, per_week, m.target_low, m.target_high, status))
    return out


def unmapped_exercises(conn: Connection, now: datetime, days: int = 90) -> list[str]:
    return list(conn.execute(text(
        "select distinct e.name from gym_sets s join activities a on a.id = s.workout_id join exercises e on e.id = s.exercise_id "
        "where a.start_at > :since and a.start_at <= :now "
        "and not exists (select 1 from library_muscles lm where lm.exercise_name = e.name) order by e.name"
    ), _gym_window(days, now)).scalars())
