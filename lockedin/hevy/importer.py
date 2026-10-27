import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import timedelta

from sqlalchemy import Connection, text

from lockedin.dedupe import resolve_overlaps
from lockedin.hevy.parse import HevyParseResult, HevySet, HevyWorkout
from lockedin.timeutil import TZ

MOVED_WITHOUT_END = timedelta(hours=2)


@dataclass
class HevyImportResult:
    new: int
    updated: int
    unchanged: int
    skipped: list[tuple[int, str]]


E1RM_MAX_REPS = 20  # past this Epley is too rough even to pick a working weight from
PR_MAX_REPS = 12  # bests and goals only trust sets in a strength range (Epley drifts past ~10–12 reps)


def e1rm(s: HevySet) -> float | None:
    """Epley estimated 1-rep max. None for warmups, bodyweight-only and high-rep sets, and assisted lifts
    (their weight is help, so more of it isn't stronger)."""
    if (s.set_type == "warmup" or not s.weight_kg or not s.reps or not 1 <= s.reps <= E1RM_MAX_REPS
            or "assisted" in s.exercise_title.lower()):
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


def _key(w: HevyWorkout) -> str:
    return f"{w.start_at.isoformat()}|{w.title}"


def _same_workout(w: HevyWorkout, row) -> bool:
    """Renamed (same start), or its times edited in Hevy (same title, mostly the same span; without end
    times, within MOVED_WITHOUT_END of the old start on the same day)."""
    if row.start_at == w.start_at:
        return True
    if row.title != w.title:
        return False
    if not w.end_given:
        return (abs(row.start_at - w.start_at) <= MOVED_WITHOUT_END
                and row.start_at.astimezone(TZ).date() == w.start_at.astimezone(TZ).date())
    shared = min(row.end_at, w.end_at) - max(row.start_at, w.start_at)
    return shared > timedelta(0) and shared > 0.5 * min(row.end_at - row.start_at, w.end_at - w.start_at)


def _match(conn: Connection, w: HevyWorkout, exported: set[str], claimed: set[int]):
    """The stored workout this one is: by key, else one edited in Hevy since. A stored workout whose key is
    also in this export, or already matched, is someone else's, so two workouts never merge into one."""
    row = conn.execute(text("select activity_id, content_hash, hevy_key from gym_workouts where hevy_key = :k"),
                       {"k": _key(w)}).first()
    if row:
        return row
    near = conn.execute(text(
        "select g.activity_id, g.content_hash, g.hevy_key, g.title, a.start_at, a.end_at from gym_workouts g "
        "join activities a on a.id = g.activity_id where a.source = 'hevy' "
        "and a.start_at < :end + interval '1 day' and a.end_at > :start - interval '1 day'"
    ), {"start": w.start_at, "end": w.end_at}).all()
    near = [r for r in near if r.hevy_key not in exported and r.activity_id not in claimed and _same_workout(w, r)]
    near.sort(key=lambda r: (r.start_at != w.start_at, abs(r.start_at - w.start_at)))
    return near[0] if near else None


def import_hevy(conn: Connection, parsed: HevyParseResult) -> HevyImportResult:
    result = HevyImportResult(0, 0, 0, parsed.skipped)
    exported = {_key(w) for w in parsed.workouts}
    claimed: set[int] = set()
    for w in parsed.workouts:
        key = _key(w)
        digest = _content_hash(w)
        times = {"start": w.start_at, "end": w.end_at, "dur": int((w.end_at - w.start_at).total_seconds())}
        row = _match(conn, w, exported, claimed)
        if row:
            claimed.add(row.activity_id)
        if row and row.content_hash == digest and row.hevy_key == key:  # a moved start isn't in the hash
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
