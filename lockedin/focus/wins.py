"""Things worth celebrating (recent personal bests, consistency) and things that have stalled."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import Connection, text

from lockedin.focus.sessions import Session, counted, counted_sessions
from lockedin.hevy.importer import PR_MAX_REPS
from lockedin.timeutil import TZ

EPOCH = datetime(2000, 1, 1, tzinfo=TZ)
MAX_WINS = 6
MIN_RUN_M = 3000
MIN_SWIM_M = 400
SAME_DISTANCE = 0.10  # a pace best only counts against runs/swims within 10% of its distance (a 3k isn't a 10k)
CONSISTENCY_WEEKS = 8
YEAR = timedelta(days=365)


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
        f"join exercises e on e.id = s.exercise_id where s.e1rm is not null and s.reps <= {PR_MAX_REPS} and {counted('a')} "
        "and a.start_at <= :now) "
        "select name, (array_agg(aid order by e1rm desc))[1] as aid, (array_agg(start_at order by e1rm desc))[1] as at, "
        "max(e1rm) as best, (select max(e1rm) from sets p where p.name = sets.name and p.start_at <= :since) as prior "
        "from sets where start_at > :since group by name"
    ), {"since": since, "now": now}).all()
    return [Win("e1rm_pr", f"New best: {r.name}", f"est. 1RM {r.best:.1f} kg (was {r.prior:.1f})", _local(r.at), r.aid)
            for r in rows if r.prior and r.best > r.prior]


def _faster(window: list[Session], before: list[Session], pace) -> tuple[Session, float, float] | None:
    """(session, its pace, the best earlier pace) for the window session that beat earlier ones of about the same
    distance by the most."""
    out = None
    for s in window:
        near = [pace(o) for o in before if pace(o) and abs(o.distance_m - s.distance_m) <= SAME_DISTANCE * s.distance_m]
        if pace(s) and near and pace(s) < min(near) and (out is None or pace(s) / min(near) < out[1] / out[2]):
            out = (s, pace(s), min(near))
    return out


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

    def of(sport, least):
        return lambda items: [s for s in items if s.sport == sport and (s.distance_m or 0) >= least]

    runs, swims = of("run", MIN_RUN_M), of("swim", MIN_SWIM_M)
    if found := _faster(runs(window), runs(before), lambda s: s.avg_pace_s_per_km):
        s, pace, was = found
        wins.append(Win("fastest_run", "Fastest run", f"{_pace(pace)} /km over {s.distance_m / 1000:.1f} km (was {_pace(was)})",
                        _local(s.start_at), s.id))
    if found := _faster(swims(window), swims(before), lambda s: s.swim_pace_s_per_100m):
        s, pace, was = found
        wins.append(Win("swim_pace", "Fastest swim", f"{_pace(pace)} /100m over {s.distance_m:.0f} m (was {_pace(was)})",
                        _local(s.start_at), s.id))

    # Sessions a week over 8 weeks against the same 8 weeks a year ago, so one busy (or holiday) month doesn't decide it.
    span = timedelta(weeks=CONSISTENCY_WEEKS)
    recent = len(counted_sessions(conn, now - span, now)) / CONSISTENCY_WEEKS
    last_year = len(counted_sessions(conn, now - YEAR - span, now - YEAR)) / CONSISTENCY_WEEKS
    if last_year and round(recent, 1) > round(last_year, 1):
        wins.append(Win("consistency", "More consistent than last year",
                        f"{recent:.1f} sessions a week over the last {CONSISTENCY_WEEKS} weeks (was {last_year:.1f})",
                        _local(now), None))

    return sorted(wins, key=lambda w: w.date, reverse=True)[:MAX_WINS]


def _stalled(conn: Connection, now: datetime) -> list[tuple[str, float]]:
    """(exercise, best earlier e1RM) for lifts done 4+ times in 6 weeks without beating the 6 weeks before."""
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
            out.append((name, max(earlier)))
    return out


def stalled_exercises(conn: Connection, now: datetime) -> list[str]:
    return [name for name, _ in _stalled(conn, now)]


def _gym_plateaus(conn: Connection, now: datetime) -> list[Plateau]:
    return [Plateau("gym", f"{name} has stalled", f"Best est. 1RM {best:.1f} kg, not beaten in 6 weeks",
                    "Change the stimulus for 3–4 weeks: try 4 × 6–8 a bit heavier, or swap to a variation.")
            for name, best in _stalled(conn, now)]


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
