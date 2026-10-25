"""Add-on gym suggestions for under-trained muscles: an exercise, sets × reps and a weight when one can be justified."""

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from sqlalchemy import Connection, text

from lockedin.focus.coverage import muscle_coverage
from lockedin.focus.sessions import counted

TARGET_REPS = 12          # 12 reps at full effort ≈ 10 reps at RPE 8, so "3 × 8–12" stays honest
NEW_EXERCISE_FACTOR = 0.8  # never-done exercises start light
RECENT_DAYS = 90
E1RM_DAYS = 56


@dataclass
class GymSuggestion:
    muscle_key: str
    muscle_name: str
    exercise: str
    sets: int
    reps: str
    weight_kg: float | None
    dumbbell: Literal["pair", "each"] | None  # same convention as the owner's Hevy logs; None = not a dumbbell exercise
    estimate: bool
    reason: str


def _round_down(kg: float) -> float:
    step = 2.5 if kg >= 20 else 1.0
    return math.floor(kg / step + 1e-9) * step


def suggested_load(e1rm: float, reps: int = TARGET_REPS) -> float:
    return _round_down(e1rm / (1 + reps / 30))


def _fmt(x: float) -> str:
    return f"{x:g}"


def _best_e1rm(conn: Connection, name: str, now: datetime) -> float | None:
    for days in (E1RM_DAYS, RECENT_DAYS):
        best = conn.execute(text(
            "select max(s.e1rm) from gym_sets s join activities a on a.id = s.workout_id join exercises e on e.id = s.exercise_id "
            f"where e.name = :n and {counted('a')} and a.start_at > :since and a.start_at <= :now"
        ), {"n": name, "since": now - timedelta(days=days), "now": now}).scalar()
        if best:
            return float(best)
    return None


def _best_reps(conn: Connection, name: str, now: datetime) -> int | None:
    return conn.execute(text(
        "select max(s.reps) from gym_sets s join activities a on a.id = s.workout_id join exercises e on e.id = s.exercise_id "
        f"where e.name = :n and s.set_type <> 'warmup' and {counted('a')} and a.start_at > :since and a.start_at <= :now"
    ), {"n": name, "since": now - timedelta(days=RECENT_DAYS), "now": now}).scalar()


def _pick(conn: Connection, muscle: str, now: datetime) -> tuple[str, str, float | None, bool, int | None] | None:
    """(exercise, equipment, weight, estimate, best_reps) for one muscle, preferring what the owner already does."""
    own = conn.execute(text(
        "select e.name, le.equipment, max(a.start_at) as last from gym_sets s join activities a on a.id = s.workout_id "
        "join exercises e on e.id = s.exercise_id join library_exercises le on le.name = e.name "
        "join library_muscles lm on lm.exercise_name = e.name and lm.role = 'primary' and lm.muscle_key = :m "
        f"where {counted('a')} and a.start_at > :since and a.start_at <= :now group by e.name, le.equipment order by last desc limit 1"
    ), {"m": muscle, "since": now - timedelta(days=RECENT_DAYS), "now": now}).first()
    if own:
        best = _best_e1rm(conn, own.name, now)
        weight = suggested_load(best) if best and own.equipment != "bodyweight" else None
        return own.name, own.equipment, weight, False, _best_reps(conn, own.name, now)

    library = conn.execute(text(
        "select le.name, le.equipment, le.related_to, le.ratio from library_exercises le "
        "join library_muscles lm on lm.exercise_name = le.name and lm.role = 'primary' and lm.muscle_key = :m "
        "order by le.ratio desc nulls last, le.name"
    ), {"m": muscle}).all()
    for ex in library:
        if ex.related_to and ex.ratio:
            related = _best_e1rm(conn, ex.related_to, now)
            if related:
                return ex.name, ex.equipment, _round_down(suggested_load(related * ex.ratio) * NEW_EXERCISE_FACTOR), True, None
    if library:
        ex = library[0]
        return ex.name, ex.equipment, None, True, None
    return None


def gym_suggestions(conn: Connection, now: datetime, limit: int = 3) -> list[GymSuggestion]:
    coverage = muscle_coverage(conn, now)
    dumbbell_logging = conn.execute(text("select dumbbell_weights from profile where id = 1")).scalar() or "pair"
    low = [c for c in coverage if c.status == "low"]
    low.sort(key=lambda c: (-(c.target_low - c.sets_per_week) / c.target_low, coverage.index(c)))
    out = []
    for c in low[:limit]:
        picked = _pick(conn, c.key, now)
        if not picked:
            continue
        name, equipment, weight, estimate, best_reps = picked
        reps = f"{round(best_reps * 0.8)}–{best_reps}" if equipment == "bodyweight" and best_reps else "8–12"
        out.append(GymSuggestion(
            muscle_key=c.key, muscle_name=c.name, exercise=name, sets=3, reps=reps,
            weight_kg=None if equipment == "bodyweight" else weight,
            dumbbell=dumbbell_logging if equipment == "dumbbell" else None,
            estimate=estimate, reason=f"{c.name}: {_fmt(c.sets_per_week)} sets/week, aim for {_fmt(c.target_low)}–{_fmt(c.target_high)}"))
    return out
