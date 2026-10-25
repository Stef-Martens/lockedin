"""Builders for focus-engine tests: insert sessions directly, no FIT/CSV parsing."""

from datetime import datetime, timedelta

from sqlalchemy import text

from lockedin.hevy.importer import e1rm
from lockedin.hevy.parse import HevySet


def add_session(conn, sport: str, start: datetime, duration_s: int, *, source: str = "healthfit",
                sub_type: str | None = None, distance_m: float | None = None, avg_hr: int | None = None,
                max_hr: int | None = None, np: float | None = None, avg_power: int | None = None,
                best_20m_power: float | None = None, swim_pace: float | None = None, avg_pace: float | None = None,
                power: list | None = None, hr: list | None = None, superseded_by: int | None = None) -> int:
    aid = conn.execute(text(
        "insert into activities (source, source_ref, sport, sub_type, start_at, end_at, duration_s, moving_s, distance_m, "
        "avg_hr, max_hr, np, avg_power, best_20m_power, swim_pace_s_per_100m, avg_pace_s_per_km, superseded_by) "
        "values (:source, gen_random_uuid()::text, :sport, :sub_type, :start, :end, :dur, :dur, :dist, :avg_hr, :max_hr, "
        ":np, :avg_power, :b20, :swim, :pace, :sup) returning id"
    ), {"source": source, "sport": sport, "sub_type": sub_type, "start": start, "end": start + timedelta(seconds=duration_s),
        "dur": duration_s, "dist": distance_m, "avg_hr": avg_hr, "max_hr": max_hr, "np": np, "avg_power": avg_power,
        "b20": best_20m_power, "swim": swim_pace, "pace": avg_pace, "sup": superseded_by}).scalar_one()
    if power is not None or hr is not None:
        n = len(power if power is not None else hr)
        conn.execute(text(
            "insert into activity_streams (activity_id, t_offset, power, hr) values "
            "(:i, cast(:t as integer[]), cast(:p as smallint[]), cast(:h as smallint[]))"
        ), {"i": aid, "t": list(range(n)), "p": power, "h": hr})
    return aid


def add_gym(conn, start: datetime, sets: list[tuple[str, float | None, int, str]], *, title: str = "Gym",
            duration_s: int = 3600) -> int:
    aid = add_session(conn, "gym", start, duration_s, source="hevy", sub_type="strength")
    conn.execute(text("insert into gym_workouts (activity_id, hevy_key, title, content_hash) values (:i, :k, :t, 'x')"),
                 {"i": aid, "k": f"{start.isoformat()}|{title}", "t": title})
    order: dict[str, int] = {}
    for i, (name, kg, reps, set_type) in enumerate(sets):
        ex = conn.execute(text("insert into exercises (name) values (:n) on conflict (name) do update set name = excluded.name "
                               "returning id"), {"n": name}).scalar_one()
        o = order.setdefault(name, len(order))
        s = HevySet(name, o, i, set_type, kg, reps, None, None, None, None, None)
        conn.execute(text("insert into gym_sets (workout_id, exercise_id, exercise_order, set_index, set_type, weight_kg, reps, e1rm) "
                          "values (:w, :e, :o, :i, :t, :kg, :r, :x)"),
                     {"w": aid, "e": ex, "o": o, "i": i, "t": set_type, "kg": kg, "r": reps, "x": e1rm(s)})
    return aid
