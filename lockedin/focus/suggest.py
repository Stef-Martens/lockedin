"""Add-on gym suggestions for under-trained muscles: an exercise, sets × reps and a weight when one can be justified."""

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from sqlalchemy import Connection, text

from lockedin.focus.coverage import muscle_coverage
from lockedin.focus.preferences import load_preferences
from lockedin.focus.sessions import counted
from lockedin.goals.steer import goal_muscles
from lockedin.plan.steps import gap_cut

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
    goal: str | None = None  # the active goal this helps, if any


def round_down(kg: float) -> float:
    step = 2.5 if kg >= 20 else 1.0
    return math.floor(kg / step + 1e-9) * step


def _load(e1rm: float, reps: int = TARGET_REPS) -> float:
    return e1rm / (1 + reps / 30)


def suggested_load(e1rm: float, reps: int = TARGET_REPS) -> float:
    return round_down(_load(e1rm, reps))


def dumbbell_weight(raw: float, logged_as: str) -> float:
    """Whole kilos per hand, rounded down, so the suggestion names a dumbbell that exists."""
    per_hand = math.floor((raw / 2 if logged_as == "pair" else raw) + 1e-9)
    return float(per_hand * 2 if logged_as == "pair" else per_hand)


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


def pick(conn: Connection, muscle: str, now: datetime, never: frozenset[str] = frozenset(),
         skip: frozenset[str] = frozenset()) -> tuple[str, str, float | None, bool, int | None] | None:
    """(exercise, equipment, weight, estimate, best_reps) for one muscle, preferring what the owner already does.
    `never` (never-suggest) and `skip` (e.g. already in the plan) exercises are passed over."""
    excluded = never | skip
    own = conn.execute(text(
        "select e.name, le.equipment, max(a.start_at) as last from gym_sets s join activities a on a.id = s.workout_id "
        "join exercises e on e.id = s.exercise_id join library_exercises le on le.name = e.name "
        "join library_muscles lm on lm.exercise_name = e.name and lm.role = 'primary' and lm.muscle_key = :m "
        f"where {counted('a')} and a.start_at > :since and a.start_at <= :now and e.name <> all(cast(:excluded as text[])) "
        "group by e.name, le.equipment order by last desc limit 1"
    ), {"m": muscle, "since": now - timedelta(days=RECENT_DAYS), "now": now, "excluded": list(excluded)}).first()
    if own:
        best = _best_e1rm(conn, own.name, now)
        # Left for weeks: start lighter (see plan.steps).
        weight = _load(best) * (1 - gap_cut((now - own.last).days)) if best and own.equipment != "bodyweight" else None
        return own.name, own.equipment, weight, False, _best_reps(conn, own.name, now)

    library = conn.execute(text(
        "select le.name, le.equipment, le.related_to, le.ratio from library_exercises le "
        "join library_muscles lm on lm.exercise_name = le.name and lm.role = 'primary' and lm.muscle_key = :m "
        "where le.name <> all(cast(:excluded as text[])) order by le.ratio desc nulls last, le.name"
    ), {"m": muscle, "excluded": list(excluded)}).all()
    for ex in library:
        if ex.related_to and ex.ratio:
            related = _best_e1rm(conn, ex.related_to, now)
            if related:
                return ex.name, ex.equipment, _load(related * ex.ratio) * NEW_EXERCISE_FACTOR, True, None
    if library:
        ex = library[0]
        return ex.name, ex.equipment, None, True, None
    return None


def weighted_pick(conn: Connection, muscle: str, now: datetime, dumbbell_logging: str,
                  never: frozenset[str] = frozenset(), skip: frozenset[str] = frozenset()) -> dict | None:
    """An exercise for `muscle` with its prescription: {exercise, equipment, sets, reps, weight_kg, dumbbell, estimate}."""
    picked = pick(conn, muscle, now, never, skip)
    if not picked:
        return None
    name, equipment, raw, estimate, best_reps = picked
    if raw is None or equipment == "bodyweight":
        weight = None
    elif equipment == "dumbbell":
        weight = dumbbell_weight(raw, dumbbell_logging)
    else:
        weight = round_down(raw)
    reps = f"{round(best_reps * 0.8)}–{best_reps}" if equipment == "bodyweight" and best_reps else "8–12"
    return {"exercise": name, "equipment": equipment, "sets": 3, "reps": reps, "weight_kg": weight,
            "dumbbell": dumbbell_logging if equipment == "dumbbell" else None, "estimate": estimate}


def low_muscles(conn: Connection, now: datetime, avoid: list[str]) -> list:
    """Muscles below their weekly target (28-day average), biggest shortfall first; left-out muscles excluded."""
    coverage = muscle_coverage(conn, now)
    low = [c for c in coverage if c.status == "low" and c.key not in avoid]
    low.sort(key=lambda c: (-(c.target_low - c.sets_per_week) / c.target_low, coverage.index(c)))
    return low


def low_reason(c) -> str:
    return f"{c.name}: {_fmt(c.sets_per_week)} sets/week, aim for {_fmt(c.target_low)}–{_fmt(c.target_high)}"


def gym_suggestions(conn: Connection, now: datetime, limit: int = 3) -> list[GymSuggestion]:
    prefs = load_preferences(conn)
    never = frozenset(prefs.never_exercises)
    dumbbell_logging = conn.execute(text("select dumbbell_weights from profile where id = 1")).scalar() or "pair"
    helps = goal_muscles(conn, now)
    low = goal_first(low_muscles(conn, now, prefs.avoid_muscles), helps)
    out = []
    for c in low[:limit]:
        p = weighted_pick(conn, c.key, now, dumbbell_logging, never)
        if not p:
            continue
        goal = helps[c.key][0] if c.key in helps else None
        out.append(GymSuggestion(
            muscle_key=c.key, muscle_name=c.name, exercise=p["exercise"], sets=p["sets"], reps=p["reps"],
            weight_kg=p["weight_kg"], dumbbell=p["dumbbell"], estimate=p["estimate"],
            reason=low_reason(c) + (f" · helps: {goal}" if goal else ""), goal=goal))
    return out


def goal_first(low: list, helps: dict[str, list[str]]) -> list:
    """Same order, but muscles that an active goal lift trains come first."""
    return [c for c in low if c.key in helps] + [c for c in low if c.key not in helps]
