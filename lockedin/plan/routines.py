"""Routines learned from Hevy: a workout started from a routine carries the routine's name as its title."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import Connection, text

from lockedin.focus.sessions import counted

ROUTINE_WINDOW = timedelta(days=60)


@dataclass
class RoutineExercise:
    name: str
    sets: int
    last_sets: list[tuple[float | None, int | None]]  # working (kg, reps) in order; warm-ups left out


@dataclass
class Routine:
    title: str
    activity_id: int
    last_done: datetime
    exercises: list[RoutineExercise]


def _exercises(conn: Connection, activity_id: int) -> list[RoutineExercise]:
    out: dict[int, RoutineExercise] = {}
    for r in conn.execute(text(
        "select e.name, s.exercise_order, s.set_type, s.weight_kg, s.reps from gym_sets s "
        "join exercises e on e.id = s.exercise_id where s.workout_id = :a order by s.exercise_order, s.set_index"
    ), {"a": activity_id}):
        ex = out.setdefault(r.exercise_order, RoutineExercise(r.name, 0, []))
        if r.set_type != "warmup":
            ex.sets += 1
            ex.last_sets.append((r.weight_kg, r.reps))
    return [ex for ex in out.values() if ex.sets]


def routines(conn: Connection, now: datetime) -> list[Routine]:
    """Every workout title used in the last 60 days, newest first, shaped like its latest workout."""
    rows = conn.execute(text(
        "select distinct on (w.title) w.title, a.id, a.start_at from gym_workouts w "
        f"join activities a on a.id = w.activity_id where {counted('a')} "
        "and a.start_at > :since and a.start_at <= :now order by w.title, a.start_at desc"
    ), {"since": now - ROUTINE_WINDOW, "now": now}).all()
    rows.sort(key=lambda r: r.start_at, reverse=True)
    return [Routine(r.title, r.id, r.start_at, _exercises(conn, r.id)) for r in rows]


def latest_sets(conn: Connection, now: datetime, exercise: str) -> list[tuple[float | None, int | None]]:
    """Working (kg, reps) from the latest counted session with this exercise, whatever the workout was called."""
    aid = conn.execute(text(
        "select a.id from gym_sets s join exercises e on e.id = s.exercise_id join activities a on a.id = s.workout_id "
        f"where e.name = :n and s.set_type <> 'warmup' and {counted('a')} and a.start_at <= :now "
        "order by a.start_at desc limit 1"
    ), {"n": exercise, "now": now}).scalar()
    if aid is None:
        return []
    return [(r.weight_kg, r.reps) for r in conn.execute(text(
        "select s.weight_kg, s.reps from gym_sets s join exercises e on e.id = s.exercise_id "
        "where s.workout_id = :a and e.name = :n and s.set_type <> 'warmup' order by s.set_index"
    ), {"a": aid, "n": exercise})]


def last_logged(conn: Connection, now: datetime, exercise: str) -> datetime | None:
    """When this exercise last had a working set, in any counted workout."""
    return conn.execute(text(
        "select max(a.start_at) from gym_sets s join exercises e on e.id = s.exercise_id join activities a on a.id = s.workout_id "
        f"where e.name = :n and s.set_type <> 'warmup' and {counted('a')} and a.start_at <= :now"
    ), {"n": exercise, "now": now}).scalar()


def routine(conn: Connection, now: datetime, title: str) -> Routine | None:
    return next((r for r in routines(conn, now) if r.title == title), None)
