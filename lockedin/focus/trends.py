"""Per-sport series for the Trends pages. Counted sessions only; dates are Brussels-local."""

from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy import Connection, text

from lockedin.fitness import ftp_at
from lockedin.focus.mix import effort_mix
from lockedin.focus.sessions import counted, counted_sessions
from lockedin.timeutil import TZ, week_start


def _since(now: datetime, weeks: int) -> datetime:
    first = week_start(now) - timedelta(weeks=weeks - 1)
    return datetime.combine(first, datetime.min.time(), tzinfo=TZ) - timedelta(microseconds=1)


def _weekly(now: datetime, weeks: int, values: dict, key: str, scale: float = 1.0, ndigits: int = 1) -> list[dict]:
    first = week_start(now) - timedelta(weeks=weeks - 1)
    return [{"week_start": first + timedelta(weeks=i), key: round(values.get(first + timedelta(weeks=i), 0) * scale, ndigits)}
            for i in range(weeks)]


def _ratio(a, b, ndigits=3):
    return round(a / b, ndigits) if a and b else None


def bike_trends(conn: Connection, now: datetime, weeks: int = 26) -> dict:
    rides = counted_sessions(conn, _since(now, weeks), now, "bike")
    minutes, tss = defaultdict(float), defaultdict(float)
    tss_by_id = dict(conn.execute(text("select id, tss from activities where id = any(:ids)"),
                                  {"ids": [r.id for r in rides]}).all()) if rides else {}
    for r in rides:
        minutes[week_start(r.start_at)] += r.duration_s / 60
        tss[week_start(r.start_at)] += tss_by_id.get(r.id) or 0
    weekly = _weekly(now, weeks, minutes, "minutes", ndigits=0)
    for row, t in zip(weekly, _weekly(now, weeks, tss, "tss", ndigits=0)):
        row["tss"] = t["tss"]
    return {
        "rides": [{"id": r.id, "date": r.start_at.astimezone(TZ).date(), "np": r.np, "avg_power": r.avg_power,
                   "avg_hr": r.avg_hr, "efficiency": _ratio(r.np, r.avg_hr), "best_20m": r.best_20m_power} for r in rides],
        "weekly": weekly,
        "ftp": ftp_at(conn, now),
        "mix": effort_mix(conn, now, "bike"),
    }


def run_trends(conn: Connection, now: datetime, weeks: int = 26) -> dict:
    runs = counted_sessions(conn, _since(now, weeks), now, "run")
    km = defaultdict(float)
    for r in runs:
        km[week_start(r.start_at)] += (r.distance_m or 0) / 1000
    return {
        "runs": [{"id": r.id, "date": r.start_at.astimezone(TZ).date(), "pace_s_per_km": r.avg_pace_s_per_km,
                  "avg_hr": r.avg_hr, "distance_m": r.distance_m,
                  # metres per minute per heartbeat: same pace at a lower HR (or faster at the same HR) = fitter
                  "aerobic_efficiency": _ratio(60_000 / r.avg_pace_s_per_km, r.avg_hr) if r.avg_pace_s_per_km else None}
                 for r in runs],
        "weekly": _weekly(now, weeks, km, "km"),
        "mix": effort_mix(conn, now, "run"),
    }


def swim_trends(conn: Connection, now: datetime, weeks: int = 26) -> dict:
    swims = counted_sessions(conn, _since(now, weeks), now, "swim")
    metres = defaultdict(float)
    for s in swims:
        metres[week_start(s.start_at)] += s.distance_m or 0
    return {
        "swims": [{"id": s.id, "date": s.start_at.astimezone(TZ).date(), "distance_m": s.distance_m,
                   "pace_s_per_100m": s.swim_pace_s_per_100m} for s in swims],
        "weekly": _weekly(now, weeks, metres, "m", ndigits=0),
    }


def gym_exercise_progress(conn: Connection, exercise_id: int) -> dict:
    name = conn.execute(text("select name from exercises where id = :i"), {"i": exercise_id}).scalar()
    rows = conn.execute(text(
        "select distinct on (a.id) a.start_at, s.e1rm, s.weight_kg, s.reps from gym_sets s join activities a on a.id = s.workout_id "
        f"where s.exercise_id = :e and s.e1rm is not null and {counted('a')} order by a.id, s.e1rm desc"
    ), {"e": exercise_id}).all()
    sessions = sorted(rows, key=lambda r: r.start_at)
    return {"exercise": name, "sessions": [
        {"date": r.start_at.astimezone(TZ).date(), "best_e1rm": round(r.e1rm, 1),
         "best_set": {"weight_kg": r.weight_kg, "reps": r.reps}} for r in sessions]}


def gym_weekly_volume(conn: Connection, now: datetime, weeks: int = 26) -> list[dict]:
    rows = conn.execute(text(
        "select a.start_at, sum(s.weight_kg * s.reps) from gym_sets s join activities a on a.id = s.workout_id "
        f"where {counted('a')} and a.start_at > :since and a.start_at <= :now and s.set_type <> 'warmup' "
        "and s.weight_kg is not null and s.reps is not null group by a.id, a.start_at"
    ), {"since": _since(now, weeks), "now": now}).all()
    volume = defaultdict(float)
    for start, kg in rows:
        volume[week_start(start)] += kg
    return _weekly(now, weeks, volume, "volume_kg", ndigits=0)
