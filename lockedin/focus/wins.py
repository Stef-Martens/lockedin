"""Things worth celebrating (recent personal bests, consistency) and things that have stalled."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import Connection, text

from lockedin.focus.sessions import counted, counted_sessions
from lockedin.timeutil import TZ

EPOCH = datetime(2000, 1, 1, tzinfo=TZ)
MAX_WINS = 6
MIN_RUN_M = 3000
MIN_SWIM_M = 400


@dataclass
class Win:
    kind: str
    title: str
    detail: str
    date: date
    activity_id: int | None


@dataclass
class Plateau:
    kind: str
    title: str
    detail: str
    suggestion: str


def _pace(s: float) -> str:
    s = round(s)
    return f"{s // 60}:{s % 60:02d}"


def _local(dt: datetime) -> date:
    return dt.astimezone(TZ).date()


def _gym_prs(conn: Connection, since: datetime, now: datetime) -> list[Win]:
    rows = conn.execute(text(
        "with sets as (select e.name, a.id as aid, a.start_at, s.e1rm from gym_sets s join activities a on a.id = s.workout_id "
        f"join exercises e on e.id = s.exercise_id where s.e1rm is not null and {counted('a')} and a.start_at <= :now) "
        "select name, (array_agg(aid order by e1rm desc))[1] as aid, (array_agg(start_at order by e1rm desc))[1] as at, "
        "max(e1rm) as best, (select max(e1rm) from sets p where p.name = sets.name and p.start_at <= :since) as prior "
        "from sets where start_at > :since group by name"
    ), {"since": since, "now": now}).all()
    return [Win("e1rm_pr", f"New best: {r.name}", f"est. 1RM {r.best:.1f} kg (was {r.prior:g})", _local(r.at), r.aid)
            for r in rows if r.prior and r.best > r.prior]


def recent_wins(conn: Connection, now: datetime, days: int = 14) -> list[Win]:
    since = now - timedelta(days=days)
    before = counted_sessions(conn, EPOCH, since)
    window = counted_sessions(conn, since, now)
    wins = _gym_prs(conn, since, now)

    def best(items, key, pick=max):
        vals = [(key(s), s) for s in items if key(s)]
        return pick(vals, key=lambda v: v[0]) if vals else None

    rides_before = [s for s in before if s.sport == "bike"]
    rides_now = [s for s in window if s.sport == "bike"]
    now_best, prior = best(rides_now, lambda s: s.best_20m_power), best(rides_before, lambda s: s.best_20m_power)
    if now_best and prior and now_best[0] > prior[0]:
        s = now_best[1]
        wins.append(Win("power_pr", "Best 20-min power", f"{now_best[0]:.0f} W (was {prior[0]:.0f})", _local(s.start_at), s.id))

    for sport, noun in (("bike", "ride"), ("run", "run")):
        cur = best([s for s in window if s.sport == sport], lambda s: s.distance_m)
        old = best([s for s in before if s.sport == sport], lambda s: s.distance_m)
        if cur and old and cur[0] > old[0]:
            wins.append(Win("longest", f"Longest {noun}", f"{cur[0] / 1000:.1f} km {noun} (was {old[0] / 1000:.1f})",
                            _local(cur[1].start_at), cur[1].id))

    def runs(items):
        return [s for s in items if s.sport == "run" and (s.distance_m or 0) >= MIN_RUN_M]

    cur, old = best(runs(window), lambda s: s.avg_pace_s_per_km, min), best(runs(before), lambda s: s.avg_pace_s_per_km, min)
    if cur and old and cur[0] < old[0]:
        wins.append(Win("fastest_run", "Fastest run", f"{_pace(cur[0])} /km (was {_pace(old[0])})", _local(cur[1].start_at), cur[1].id))

    def swims(items):
        return [s for s in items if s.sport == "swim" and (s.distance_m or 0) >= MIN_SWIM_M]

    cur, old = best(swims(window), lambda s: s.swim_pace_s_per_100m, min), best(swims(before), lambda s: s.swim_pace_s_per_100m, min)
    if cur and old and cur[0] < old[0]:
        wins.append(Win("swim_pace", "Fastest swim", f"{_pace(cur[0])} /100m (was {_pace(old[0])})", _local(cur[1].start_at), cur[1].id))

    month = len(counted_sessions(conn, now - timedelta(days=28), now))
    last_year = len(counted_sessions(conn, now - timedelta(days=365 + 28), now - timedelta(days=365)))
    if last_year and month > last_year:
        wins.append(Win("consistency", "More consistent than last year",
                        f"{month} sessions in the last 4 weeks (was {last_year})", _local(now), None))

    return sorted(wins, key=lambda w: w.date, reverse=True)[:MAX_WINS]


def _gym_plateaus(conn: Connection, now: datetime) -> list[Plateau]:
    window = timedelta(days=42)
    rows = conn.execute(text(
        "select e.name, a.id as aid, a.start_at, max(s.e1rm) as best from gym_sets s join activities a on a.id = s.workout_id "
        f"join exercises e on e.id = s.exercise_id where s.e1rm is not null and {counted('a')} "
        "and a.start_at > :from_ and a.start_at <= :now group by e.name, a.id, a.start_at"
    ), {"from_": now - 2 * window, "now": now}).all()
    by_name: dict[str, list] = {}
    for r in rows:
        by_name.setdefault(r.name, []).append(r)
    out = []
    for name, sessions in sorted(by_name.items()):
        recent = [r.best for r in sessions if r.start_at > now - window]
        earlier = [r.best for r in sessions if r.start_at <= now - window]
        if len(recent) >= 4 and len(earlier) >= 2 and max(recent) <= max(earlier):
            out.append(Plateau("gym", f"{name} has stalled", f"Best est. 1RM {max(earlier):.1f} kg, not beaten in 6 weeks",
                               "Change the stimulus for 3–4 weeks: try 4 × 6–8 a bit heavier, or swap to a variation."))
    return out


def _bike_plateau(conn: Connection, now: datetime) -> list[Plateau]:
    window = timedelta(days=56)
    rides = [s for s in counted_sessions(conn, now - 2 * window, now, "bike") if s.best_20m_power]
    recent = [s.best_20m_power for s in rides if s.start_at > now - window]
    earlier = [s.best_20m_power for s in rides if s.start_at <= now - window]
    if len(recent) >= 4 and len(earlier) >= 2 and max(recent) <= max(earlier):
        return [Plateau("bike_power", "Bike power has stalled", f"Best 20-min power {max(earlier):.0f} W, not beaten in 8 weeks",
                        "Add one interval ride a week (4 × 8 min at threshold) for a month.")]
    return []


def plateaus(conn: Connection, now: datetime) -> list[Plateau]:
    return _gym_plateaus(conn, now) + _bike_plateau(conn, now)
