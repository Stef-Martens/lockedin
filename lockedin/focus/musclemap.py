"""One week on the body: gym sets per muscle, cardio as its own layer, history and each muscle's main lift."""

from dataclasses import asdict
from datetime import date, datetime, time, timedelta

from sqlalchemy import Connection, text

from lockedin.focus.coverage import CREDIT, CREDIT_FROM
from lockedin.focus.sessions import COUNTED_SQL, counted
from lockedin.focus.suggest import gym_suggestions
from lockedin.timeutil import TZ, week_start

# Cardio draws stripes on these muscles; it never adds gym sets.
CARDIO_MUSCLES = {
    "bike": ["quads", "glutes", "hamstrings", "calves"],
    "run": ["quads", "glutes", "hamstrings", "calves"],
    "swim": ["lats", "front_delt", "side_delt", "rear_delt", "triceps"],
}
HISTORY_WEEKS = 6
LIFT_WINDOW = timedelta(weeks=8)
NOT_LATELY = timedelta(days=28)
LOCAL_DAY = "(a.start_at at time zone 'Europe/Brussels')::date"


def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _local_midnight(d: date) -> datetime:
    return datetime.combine(d, time(), TZ)


def _main_lift(conn: Connection, muscle: str, candidates: list[tuple], window_end: datetime) -> dict | None:
    """The exercise with the most primary working sets in the window, and its best e1RM first vs. latest."""
    if not candidates:
        return None
    name = sorted(candidates, key=lambda c: (-c[1], -(c[2] or 0), c[0]))[0][0]
    sessions = conn.execute(text(
        "select a.start_at, max(s.e1rm) from gym_sets s join activities a on a.id = s.workout_id "
        "join exercises e on e.id = s.exercise_id "
        f"where e.name = :n and {counted('a')} and s.set_type <> 'warmup' and s.e1rm is not null "
        "and a.start_at > :since and a.start_at <= :until group by a.id, a.start_at order by a.start_at"
    ), {"n": name, "since": window_end - LIFT_WINDOW, "until": window_end}).all()
    if not sessions:
        return None
    first, latest = sessions[0], sessions[-1]
    status = ("not_lately" if window_end - latest[0] > NOT_LATELY
              else "new" if len(sessions) == 1 else "trend")
    return {"exercise": name, "first_e1rm": round(float(first[1]), 1), "latest_e1rm": round(float(latest[1]), 1),
            "status": status}


def muscle_map(conn: Connection, now: datetime, week: date | None) -> dict:
    current = week_start(now)
    start_day = current if week is None else min(_monday(week), current)
    is_current = start_day == current
    start, end = _local_midnight(start_day), _local_midnight(start_day + timedelta(days=7))
    until = now if is_current else end  # "now" for everything measured back from the selected week
    window = {"start": start, "end": end}

    days: dict[str, list] = {}
    for key, day, exercise, sets in conn.execute(text(
        f"select lm.muscle_key, {LOCAL_DAY}, e.name, sum({CREDIT}) {CREDIT_FROM} "
        "and a.start_at >= :start and a.start_at < :end group by 1, 2, 3 order by 2, min(a.start_at), 3"
    ), window):
        per_day = days.setdefault(key, [])
        if not per_day or per_day[-1]["date"] != day.isoformat():
            per_day.append({"date": day.isoformat(), "exercises": []})
        per_day[-1]["exercises"].append({"name": exercise, "sets": float(sets)})

    history_start = start_day - timedelta(weeks=HISTORY_WEEKS - 1)
    history: dict[tuple[str, date], float] = {
        (k, wk): float(v) for k, wk, v in conn.execute(text(
            f"select lm.muscle_key, date_trunc('week', a.start_at at time zone 'Europe/Brussels')::date, sum({CREDIT}) "
            f"{CREDIT_FROM} and a.start_at >= :hstart and a.start_at < :end group by 1, 2"
        ), {"hstart": _local_midnight(history_start), "end": end})}

    last_trained = dict(conn.execute(text(
        f"select lm.muscle_key, max({LOCAL_DAY}) {CREDIT_FROM} and a.start_at < :start group by 1"
    ), window).all())

    cardio = []
    for sport, seconds, sport_days in conn.execute(text(
        f"select sport, sum(duration_s), array_agg(distinct (start_at at time zone 'Europe/Brussels')::date) "
        f"from activities where {COUNTED_SQL} and sport in ('bike', 'run', 'swim') "
        "and start_at >= :start and start_at < :end group by sport"
    ), window):
        cardio.append({"sport": sport, "minutes": round(seconds / 60), "days": sorted(d.isoformat() for d in sport_days)})
    cardio.sort(key=lambda c: list(CARDIO_MUSCLES).index(c["sport"]))

    candidates: dict[str, list[tuple]] = {}
    for key, name, n, best in conn.execute(text(
        f"select lm.muscle_key, e.name, count(*), max(s.e1rm) {CREDIT_FROM} and lm.role = 'primary' "
        "and a.start_at > :since and a.start_at <= :until group by 1, 2"
    ), {"since": until - LIFT_WINDOW, "until": until}):
        candidates.setdefault(key, []).append((name, n, best))

    suggestions = {s.muscle_key: asdict(s) for s in gym_suggestions(conn, now, limit=20)} if is_current else {}
    first = conn.execute(text(
        f"select min(start_at) from activities where {COUNTED_SQL} and sport in ('gym', 'bike', 'run', 'swim')"
    )).scalar()

    muscles = []
    for m in conn.execute(text("select key, name, region, target_low, target_high from muscles order by sort")):
        trained = days.get(m.key, [])
        muscles.append({
            "key": m.key, "name": m.name, "region": m.region,
            "target_low": m.target_low, "target_high": m.target_high,
            "sets": sum(x["sets"] for d in trained for x in d["exercises"]),
            "days": trained,
            "history": [{"week_start": (history_start + timedelta(weeks=i)).isoformat(),
                         "sets": history.get((m.key, history_start + timedelta(weeks=i)), 0)}
                        for i in range(HISTORY_WEEKS)],
            "last_trained": last_trained[m.key].isoformat() if m.key in last_trained else None,
            "lift": _main_lift(conn, m.key, candidates.get(m.key, []), until),
            "cardio": [{"sport": c["sport"], "minutes": c["minutes"]} for c in cardio
                       if m.key in CARDIO_MUSCLES[c["sport"]]],
            "suggestion": suggestions.get(m.key),
        })
    return {
        "week_start": start_day.isoformat(),
        "is_current": is_current,
        "first_week": week_start(first).isoformat() if first else None,
        "trained_count": sum(1 for m in muscles if m["sets"] > 0),
        "cardio": cardio,
        "muscles": muscles,
    }
