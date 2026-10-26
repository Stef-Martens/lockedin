"""How far along a goal is, when its words say something the data can measure."""

import re
from datetime import datetime, timedelta

from sqlalchemy import Connection, text

from lockedin.fitness import ftp_at
from lockedin.focus.sessions import counted
from lockedin.plan.goals import goal_for

WINDOW = timedelta(weeks=8)
LIFT_SEARCH = timedelta(days=90)
NUMBER = re.compile(r"(\d+(?:[.,]\d+)?)\s*(kg|w\b|watts?\b|km\b|k\b|m\b|cm\b)?", re.I)
RELATIVE = re.compile(r"\b(lose|gain|drop|add|more|less|increase|decrease)\b|[+-]\s*\d", re.I)


def _numbers(goal: dict) -> list[tuple[float, str]]:
    """(value, unit) pairs from the goal's text, then its target; unit '' when none."""
    out = []
    for source in (goal.get("text") or "", goal.get("target") or ""):
        for value, unit in NUMBER.findall(source):
            out.append((float(value.replace(",", ".")), (unit or "").lower().rstrip("s")))
    return out


def _first(goal: dict, units: tuple[str, ...]) -> tuple[float, str] | None:
    return next(((v, u) for v, u in _numbers(goal) if u in units), None)


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


def goal_lift(conn: Connection, now: datetime, goal: dict) -> str | None:
    """The one lift a goal is about: the linked exercise, else the single logged lift its words point to."""
    if goal.get("exercise"):
        return goal["exercise"]
    names = conn.execute(text(
        "select distinct e.name from gym_sets s join exercises e on e.id = s.exercise_id "
        f"join activities a on a.id = s.workout_id where {counted('a')} and a.start_at > :since and a.start_at <= :now"
    ), {"since": now - LIFT_SEARCH, "now": now}).scalars().all()
    matches = [n for n in names if goal_for(n, [{**goal, "status": "active"}])]
    return matches[0] if len(matches) == 1 else None


def _longest(conn: Connection, now: datetime, sport: str) -> float | None:
    m = conn.execute(text(
        f"select max(a.distance_m) from activities a where {counted('a')} and a.sport = :s "
        "and a.start_at > :since and a.start_at <= :now"
    ), {"s": sport, "since": now - WINDOW, "now": now}).scalar()
    return float(m) if m else None


def progress(conn: Connection, now: datetime, goal: dict) -> dict | None:
    area = goal.get("area") or "general"
    lowered = (goal.get("text") or "").lower()

    lift = goal_lift(conn, now, goal) if area in ("gym", "general") or goal.get("exercise") else None
    if lift and (n := _first(goal, ("kg",))):
        best = conn.execute(text(
            "select max(s.e1rm) from gym_sets s join exercises e on e.id = s.exercise_id join activities a on a.id = s.workout_id "
            f"where e.name = :n and s.set_type <> 'warmup' and {counted('a')} and a.start_at > :since and a.start_at <= :now"
        ), {"n": lift, "since": now - WINDOW, "now": now}).scalar()
        return _result(float(best) if best else None, n[0], "kg", " est. 1RM")

    if area == "bike":
        n = _first(goal, ("w", "watt")) or (next(((v, "") for v, _ in _numbers(goal) if v >= 50), None) if "ftp" in lowered else None)
        if n:
            ftp = ftp_at(conn, now)
            return _result(round(ftp) if ftp else None, n[0], "W")

    if area in ("run", "swim"):
        n = _first(goal, ("km", "k", "m"))
        if n:
            target_km = n[0] / 1000 if n[1] == "m" else n[0]
            longest = _longest(conn, now, area)
            return _result(longest / 1000 if longest else None, target_km, "km")

    if area == "body" and not RELATIVE.search(lowered):
        n = _first(goal, ("kg", "cm"))
        if n:
            types = conn.execute(text("select id, name, unit from measurement_types where unit = :u"),
                                 {"u": n[1]}).all()
            kind = next((t for t in types if t.name.lower() in lowered), None) or \
                (next((t for t in types if t.name.lower() == "weight"), None) if n[1] == "kg" else None)
            if kind:
                values = conn.execute(text(
                    "select measured_on, value from measurements where type_id = :t order by measured_on"
                ), {"t": kind.id}).all()
                if values:
                    created = (goal.get("created_at") or now).date()
                    before = [v for d, v in values if d <= created]
                    start = before[-1] if before else values[0][1]
                    return _result(values[-1][1], n[0], n[1], start=start)
    return None
