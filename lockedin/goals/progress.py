"""How far along a goal is, when its words say something the data can measure."""

import re
from datetime import datetime, timedelta

from sqlalchemy import Connection, text

from lockedin.fitness import ftp_at
from lockedin.focus.sessions import counted
from lockedin.hevy.importer import PR_MAX_REPS
from lockedin.plan.goals import goal_for, known_exercises
from lockedin.timeutil import TZ

WINDOW = timedelta(weeks=8)
LIFT_SEARCH = timedelta(days=90)
# A number and its unit. "1.500 m" / "10,000 m" are thousands; "W/kg" is a ratio, not watts.
NUMBER = re.compile(r"(\d{1,3}(?:[.,]\d{3})+(?![.,]?\d)|\d+(?:[.,]\d+)?)\s*(kg|w(?!\s*/)\b|watts?\b|km\b|k\b|m\b|cm\b)?", re.I)
THOUSANDS = re.compile(r"^\d{1,3}(?:[.,]\d{3})+$")
# Goals about a change ("lose 5 kg", "raise FTP by 20 W", "+10 kg") have no fixed target to measure against.
RELATIVE = re.compile(r"\b(lose|gain|drop|add|more|less|increase|decrease|raise|improve)\b|\bby\s+[+-]?\d|[+-]\s*\d", re.I)
MISREAD = 0.5  # a lift/FTP target below half of today's value is almost certainly a misread number
# "for 5 reps", "x5", "× 5", "5 reps", "5x80 kg": a lift goal about a set, not a 1RM.
REPS = re.compile(r"(\d{1,2})\s*(?:reps?|repetitions?)\b|(\d{1,2})\s*[x×]\s*\d+(?:[.,]\d+)?\s*kg"
                  r"|(?:[x×]|\bfor)\s*(\d{1,2})\b(?!\s*(?:kg|weeks?|days?|months?|sets?|min|[.,:]\d))", re.I)
# Times: "25:00", "1:45 h", "1:45:00", "1h45", "2 hours", "25 min", and a bare "sub 25" / "under 2".
CLOCK = re.compile(r"\b(\d{1,2}):([0-5]\d)(?::([0-5]\d))?\s*(h(?:ours?|rs?)?\b|min(?:ute)?s?\b|′)?", re.I)
HOURS = re.compile(r"\b(\d+(?:[.,]\d+)?)\s*(?:h|hrs?|hours?)(?:\s*(\d{1,2})\s*(?:min(?:ute)?s?|m|′)?)?(?![a-z])", re.I)
MINUTES = re.compile(r"\b(\d+(?:[.,]\d+)?)\s*(?:min(?:ute)?s?\b|′)", re.I)
BARE = re.compile(r"\b(?:under|sub|below|in)[\s-]+(\d{1,3}(?:[.,]\d+)?)\b"
                  r"(?!\s*(?:[:.,]\d|k\b|km|m\b|kg|w\b|weeks?|days?|months?))", re.I)
PACE = re.compile(r"/\s*(?:km|mi|100)|\bpace\b|\bper\s+(?:km|mile|100)|km/h|kph", re.I)
NAMED = ((re.compile(r"\bhalf[\s-]*marathon\b", re.I), 21.0975), (re.compile(r"\bmarathon\b", re.I), 42.195))
# Believable pace in seconds per km: decides minutes vs hours for "sub 25" / "1:45", and drops typos.
PACE_RANGE = {"run": (150, 900), "swim": (500, 3600)}
DISTANCE_SLACK = 0.99  # a 5 km race the watch measured as 4.97 km still counts
TIME_MATCH = 1.05      # a best time is read only from an activity at most 5% longer than the goal's distance


def _numbers(goal: dict) -> list[tuple[float, str]]:
    """(value, unit) pairs from the goal's text, then its target; unit '' when none."""
    out = []
    for source in (goal.get("text") or "", goal.get("target") or ""):
        for value, unit in NUMBER.findall(source):
            number = float(re.sub(r"[.,]", "", value)) if THOUSANDS.match(value) else float(value.replace(",", "."))
            out.append((number, (unit or "").lower().rstrip("s")))
    return out


def _first(goal: dict, units: tuple[str, ...]) -> tuple[float, str] | None:
    return next(((v, u) for v, u in _numbers(goal) if u in units), None)


def _words(goal: dict) -> str:
    return f"{goal.get('text') or ''} {goal.get('target') or ''}"


def _reps(goal: dict) -> int | None:
    m = REPS.search(_words(goal))
    return int(next(g for g in m.groups() if g)) if m else None


def _num(x: str) -> float:
    return float(x.replace(",", "."))


def _times(words: str) -> list[list[int]]:
    """Each time in the words, as its possible readings in seconds ("25:00" is 25 min or 25 h; the pace decides)."""
    out: list[list[int]] = []

    def clock(m: re.Match) -> str:
        a, b, c, unit = int(m[1]), int(m[2]), m[3], (m[4] or "").lower()
        if c:
            out.append([a * 3600 + b * 60 + int(c)])
        elif unit.startswith("h"):
            out.append([a * 3600 + b * 60])
        else:
            out.append([a * 60 + b] if unit else [a * 60 + b, a * 3600 + b * 60])
        return " "

    def hours(m: re.Match) -> str:
        out.append([round(_num(m[1]) * 3600) + int(m[2] or 0) * 60])
        return " "

    def minutes(m: re.Match) -> str:
        out.append([round(_num(m[1]) * 60)])
        return " "

    words = MINUTES.sub(minutes, HOURS.sub(hours, CLOCK.sub(clock, words)))
    if not out:
        out += [[round(_num(m[1]) * 60), round(_num(m[1]) * 3600)] for m in BARE.finditer(words)]
    return out


def _target_time(words: str, km: float, sport: str) -> int | None:
    """The goal's time in seconds, when exactly one reading gives a believable pace."""
    lo, hi = PACE_RANGE[sport]
    found = {t for readings in _times(words) for t in readings if lo <= t / km <= hi}
    return found.pop() if len(found) == 1 else None


def _clock(seconds: float) -> str:
    s = round(seconds)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def _fmt(x: float) -> str:
    return f"{x:.1f}".rstrip("0").rstrip(".")


def _result(current: float | None, target: float, unit: str, suffix: str = "", start: float | None = None) -> dict | None:
    if current is None or target <= 0:
        return None
    if start is not None and start != target:
        fraction = (start - current) / (start - target)
    else:
        fraction = current / target
    return {"current": round(current, 1), "target": target, "unit": unit,
            "label": f"{_fmt(current)} / {_fmt(target)} {unit}{suffix}", "fraction": max(0.0, min(1.0, fraction))}


def logged_lifts(conn: Connection, now: datetime) -> list[str]:
    return conn.execute(text(
        "select distinct e.name from gym_sets s join exercises e on e.id = s.exercise_id "
        f"join activities a on a.id = s.workout_id where {counted('a')} and a.start_at > :since and a.start_at <= :now"
    ), {"since": now - LIFT_SEARCH, "now": now}).scalars().all()


def goal_lift(conn: Connection, now: datetime, goal: dict, names: list[str] | None = None,
              known: list[str] | None = None) -> str | None:
    """The one lift a goal is about: the linked exercise, else the single logged lift its words point to."""
    if goal.get("exercise"):
        return goal["exercise"]
    names = logged_lifts(conn, now) if names is None else names
    known = known_exercises(conn) if known is None else known
    matches = [n for n in names if goal_for(n, [{**goal, "status": "active"}], known)]
    return matches[0] if len(matches) == 1 else None


def _longest(conn: Connection, now: datetime, sport: str, window: timedelta = WINDOW) -> float | None:
    m = conn.execute(text(
        f"select max(a.distance_m) from activities a where {counted('a')} and a.sport = :s "
        "and a.start_at > :since and a.start_at <= :now"
    ), {"s": sport, "since": now - window, "now": now}).scalar()
    return float(m) if m else None


def _best_time(conn: Connection, now: datetime, sport: str, km: float, target_s: int,
               window: timedelta = WINDOW) -> dict | None:
    """Best whole-activity time over the goal's distance. Done once any activity at least that long was within the
    time; otherwise read only from activities about that long (a 10 km run holds no reliable 5 km time)."""
    rows = conn.execute(text(
        f"select a.distance_m, coalesce(a.moving_s, a.duration_s) as secs from activities a where {counted('a')} "
        "and a.sport = :s and a.distance_m >= :d and a.start_at > :since and a.start_at <= :now"
    ), {"s": sport, "d": km * 1000 * DISTANCE_SLACK, "since": now - window, "now": now}).all()
    done = [r.secs for r in rows if r.secs and r.secs <= target_s]
    close = [r.secs for r in rows if r.secs and r.distance_m <= km * 1000 * TIME_MATCH]
    best = min(done) if done else min(close, default=None)
    if best is None:
        return None
    return {"current": round(best / 60, 1), "target": round(target_s / 60, 1), "unit": "min",
            "label": f"{_clock(best)} / {_clock(target_s)} for {_fmt(km)} km", "fraction": min(1.0, target_s / best)}


def _sane(result: dict | None) -> dict | None:
    if result and result["target"] < MISREAD * result["current"]:
        return None
    return result


def progress(conn: Connection, now: datetime, goal: dict, window: timedelta = WINDOW) -> dict | None:
    """Where a measurable goal stands: the best of the `window` before `now` (8 weeks on the Overview)."""
    area = goal.get("area") or "general"
    lowered = (goal.get("text") or "").lower()
    if RELATIVE.search(lowered):
        return None

    lift = goal_lift(conn, now, goal) if area in ("gym", "general") or goal.get("exercise") else None
    if lift and (n := _first(goal, ("kg",))):
        reps = _reps(goal)
        if reps and reps > 1:  # "80 kg for 5 reps": the heaviest set of at least 5 reps, as lifted
            if "assisted" in lift.lower():  # an assistance weight: lighter is better
                return None
            best = conn.execute(text(
                "select max(s.weight_kg) from gym_sets s join exercises e on e.id = s.exercise_id "
                "join activities a on a.id = s.workout_id where e.name = :n and s.set_type <> 'warmup' and s.reps >= :r "
                f"and {counted('a')} and a.start_at > :since and a.start_at <= :now"
            ), {"n": lift, "r": reps, "since": now - window, "now": now}).scalar()
            return _sane(_result(float(best) if best else None, n[0], "kg", f" × {reps}"))
        best = conn.execute(text(
            "select max(s.e1rm) from gym_sets s join exercises e on e.id = s.exercise_id join activities a on a.id = s.workout_id "
            f"where e.name = :n and s.set_type <> 'warmup' and s.reps <= {PR_MAX_REPS} and {counted('a')} "
            "and a.start_at > :since and a.start_at <= :now"
        ), {"n": lift, "since": now - window, "now": now}).scalar()
        return _sane(_result(float(best) if best else None, n[0], "kg", " est. 1RM"))

    timed = bool(_times(_words(goal)))
    if area == "bike":
        if timed and "ftp" not in lowered:  # "250 W for 20 min", "100 km under 4 h": not something FTP answers
            return None
        n = _first(goal, ("w", "watt")) or (next(((v, "") for v, _ in _numbers(goal) if v >= 50), None) if "ftp" in lowered else None)
        if n:
            ftp = ftp_at(conn, now)
            return _sane(_result(round(ftp) if ftp else None, n[0], "W"))

    if area in ("run", "swim"):
        n = _first(goal, ("km", "k", "m"))
        named = next((km for pattern, km in NAMED if pattern.search(lowered)), None)
        if n or named:
            target_km = (n[0] / 1000 if n[1] == "m" else n[0]) if n else named
            if PACE.search(_words(goal)):
                return None
            if timed:  # "5k under 25 min": a time over the distance, or no bar rather than a wrong one
                target_s = _target_time(_words(goal), target_km, area)
                return _best_time(conn, now, area, target_km, target_s, window) if target_s else None
            longest = _longest(conn, now, area, window)
            return _result(longest / 1000 if longest else None, target_km, "km")

    if area == "body":
        n = _first(goal, ("kg", "cm"))
        if n:
            types = conn.execute(text("select id, name, unit from measurement_types where unit = :u"),
                                 {"u": n[1]}).all()
            # "chest" matches Chest; "arms" matches both Left arm and Right arm (averaged).
            kinds = [t for t in types if t.name.lower() in lowered] or \
                [t for t in types if re.search(rf"\b{re.escape(t.name.lower().split()[-1])}s?\b", lowered)] or \
                ([t for t in types if t.name.lower() == "weight"] if n[1] == "kg" else [])
            created = (goal.get("created_at") or now).date()
            starts, currents = [], []
            for kind in kinds:
                values = conn.execute(text(
                    "select measured_on, value from measurements where type_id = :t and measured_on <= :d order by measured_on"
                ), {"t": kind.id, "d": now.astimezone(TZ).date()}).all()
                if values:
                    before = [v for d, v in values if d <= created]
                    starts.append(before[-1] if before else values[0][1])
                    currents.append(values[-1][1])
            if currents:
                return _result(sum(currents) / len(currents), n[0], n[1], start=sum(starts) / len(starts))
    return None
