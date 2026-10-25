import hashlib
import json
from dataclasses import asdict, dataclass

from sqlalchemy import Connection, text

from lockedin.dedupe import resolve_overlaps
from lockedin.hevy.parse import HevyParseResult, HevySet, HevyWorkout


@dataclass
class HevyImportResult:
    new: int
    updated: int
    unchanged: int
    skipped: list[tuple[int, str]]


def e1rm(s: HevySet) -> float | None:
    """Epley estimated 1-rep max; warmups and bodyweight-only sets have none."""
    if s.set_type == "warmup" or not s.weight_kg or not s.reps or s.reps < 1:
        return None
    return s.weight_kg if s.reps == 1 else s.weight_kg * (1 + s.reps / 30)


def _content_hash(w: HevyWorkout) -> str:
    payload = {"title": w.title, "description": w.description, "end_at": w.end_at.isoformat(),
               "sets": [asdict(s) for s in w.sets]}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _insert_sets(conn: Connection, workout_id: int, sets: list[HevySet]) -> None:
    exercise_ids: dict[str, int] = {}
    for s in sets:
        if s.exercise_title not in exercise_ids:
            exercise_ids[s.exercise_title] = conn.execute(text(
                "insert into exercises (name) values (:n) on conflict (name) do update set name = excluded.name returning id"
            ), {"n": s.exercise_title}).scalar_one()
        conn.execute(text(
            "insert into gym_sets (workout_id, exercise_id, exercise_order, set_index, set_type, weight_kg, reps, "
            "distance_km, duration_s, rpe, superset_id, notes, e1rm) values (:w, :e, :o, :i, :t, :kg, :reps, "
            ":km, :dur, :rpe, :ss, :notes, :e1rm)"
        ), {"w": workout_id, "e": exercise_ids[s.exercise_title], "o": s.exercise_order, "i": s.set_index,
            "t": s.set_type, "kg": s.weight_kg, "reps": s.reps, "km": s.distance_km, "dur": s.duration_s,
            "rpe": s.rpe, "ss": s.superset_id, "notes": s.notes, "e1rm": e1rm(s)})


def import_hevy(conn: Connection, parsed: HevyParseResult) -> HevyImportResult:
    result = HevyImportResult(0, 0, 0, parsed.skipped)
    for w in parsed.workouts:
        key = f"{w.start_at.isoformat()}|{w.title}"
        digest = _content_hash(w)
        times = {"start": w.start_at, "end": w.end_at, "dur": int((w.end_at - w.start_at).total_seconds())}
        # Match on the key, or on the start time alone so a workout renamed in Hevy updates in place.
        row = conn.execute(text(
            "select g.activity_id, g.content_hash from gym_workouts g join activities a on a.id = g.activity_id "
            "where g.hevy_key = :k or (a.source = 'hevy' and a.start_at = :start) "
            "order by (g.hevy_key = :k) desc limit 1"
        ), {"k": key, "start": w.start_at}).first()
        if row and row.content_hash == digest:
            result.unchanged += 1
            continue
        if row:
            activity_id = row.activity_id
            conn.execute(text("update activities set start_at = :start, end_at = :end, duration_s = :dur, "
                              "source_ref = :k where id = :i"), {**times, "k": key, "i": activity_id})
            conn.execute(text("update gym_workouts set hevy_key = :k, title = :t, description = :d, content_hash = :h "
                              "where activity_id = :i"),
                         {"k": key, "t": w.title, "d": w.description, "h": digest, "i": activity_id})
            conn.execute(text("delete from gym_sets where workout_id = :i"), {"i": activity_id})
            result.updated += 1
        else:
            activity_id = conn.execute(text(
                "insert into activities (source, source_ref, sport, sub_type, start_at, end_at, duration_s) "
                "values ('hevy', :k, 'gym', 'strength', :start, :end, :dur) returning id"
            ), {**times, "k": key}).scalar_one()
            conn.execute(text(
                "insert into gym_workouts (activity_id, hevy_key, title, description, content_hash) "
                "values (:i, :k, :t, :d, :h)"
            ), {"i": activity_id, "k": key, "t": w.title, "d": w.description, "h": digest})
            result.new += 1
        _insert_sets(conn, activity_id, w.sets)
        resolve_overlaps(conn, activity_id)

    conn.execute(text("insert into import_log (source, summary) values ('hevy', cast(:j as jsonb))"),
                 {"j": json.dumps(asdict(result))})
    return result
