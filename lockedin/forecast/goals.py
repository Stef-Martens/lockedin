"""Each measurable goal: its weekly history, the trend ahead, and when it gets there."""

import calendar
from collections.abc import Collection
from datetime import date, datetime, timedelta

from sqlalchemy import Connection, text

from lockedin.forecast.trend import HORIZON_WEEKS, crossing, deadline, fit, month_part, project
from lockedin.goals.progress import goal_lift, progress
from lockedin.plan.goals import active_goals
from lockedin.timeoff import REGIONS, entries
from lockedin.timeutil import TZ

WEEKS_BACK = 26
WEEK = timedelta(weeks=1)
NEEDED_WITHIN = timedelta(weeks=26)  # with no date, "fast enough" means within about six months
KIND = {"kg": "lift", "W": "ftp", "km": "distance", "min": "time", "cm": "body"}


def _kind(p: dict, goal: dict) -> str:
    return "body" if goal.get("area") == "body" else KIND[p["unit"]]


def goal_category(conn: Connection, now: datetime, goal: dict, kind: str) -> str | None:
    """What time off pauses a goal: a lift by its primary muscle's region (upper/core/lower), FTP bike, a distance
    or time by its sport; body goals none (only being away pauses them)."""
    if kind == "ftp":
        return "bike"
    if kind in ("distance", "time"):
        return goal.get("area") if goal.get("area") in ("run", "bike", "swim") else None
    if kind != "lift" or not (lift := goal_lift(conn, now, goal)):
        return None
    region = conn.execute(text(
        "select m.region from library_muscles lm join muscles m on m.key = lm.muscle_key "
        "where lm.exercise_name = :n and lm.role = 'primary' order by m.sort, m.key limit 1"), {"n": lift}).scalar()
    return next((c for c, regions in REGIONS.items() if region in regions), None)


def off_days(conn: Connection, category: str | None, first: date, last: date) -> set[date]:
    """Days from `first` to `last` when `category` was or will be off, or the owner away."""
    out: set[date] = set()
    for e in entries(conn, first):
        for r in e["restrictions"]:
            if r["category"] in (category, "all"):
                d, end = max(e["start"], first), min(r["until"], last)
                out.update(d + timedelta(days=i) for i in range((end - d).days + 1))
    return out


def _history(conn: Connection, now: datetime, goal: dict, kind: str,
             off: Collection[date] = frozenset()) -> list[tuple[date, float]]:
    """One value per week: that week's best for lifts, runs and swims; for FTP and body measurements (the latest
    known value), only the weeks it changed, so a single check-in doesn't count as many weeks of data. Weeks
    ending on a day in `off` are left out."""
    out: list[tuple[date, float]] = []
    for k in range(WEEKS_BACK - 1, -1, -1):
        at = now - k * WEEK
        if at.astimezone(TZ).date() in off:
            continue
        p = progress(conn, at, goal, window=WEEK)
        if p is None or p["current"] is None:
            continue
        if kind in ("ftp", "body") and out and out[-1][1] == p["current"]:
            continue
        out.append((at.astimezone(TZ).date(), float(p["current"])))
    return out


def _rate(per_week: float, unit: str) -> str:
    if unit == "min":
        return f"{'+' if per_week > 0 else '−'}{abs(per_week) * 60:.0f} s a week"
    digits = 0 if unit == "W" else 1
    return f"{'+' if per_week > 0 else '−'}{abs(per_week):.{digits}f} {unit} a week"


def _months(early: date, late: date | None, today: date) -> str:
    """"Feb–May", "Nov–Feb 2027", or "from March on" when the cautious edge never gets there."""
    def name(d: date, with_year: bool) -> str:
        return calendar.month_abbr[d.month] + (f" {d.year}" if with_year else "")
    if late is None:
        return f"from {name(early, early.year != today.year)} on"
    if (early.year, early.month) == (late.year, late.month):
        return name(early, early.year != today.year)
    return f"{name(early, early.year != late.year)}–{name(late, late.year != today.year)}"


def _day_month(d: date) -> str:
    return f"{d.day} {calendar.month_abbr[d.month]}"


def goal_forecast(conn: Connection, now: datetime, goal: dict) -> dict | None:
    """None for goals the app can't measure (they have no bar on the Overview either)."""
    p = progress(conn, now, goal)
    if p is None:
        return None
    today = now.astimezone(TZ).date()
    kind = _kind(p, goal)
    target, current = float(p["target"]), float(p["current"])
    off = off_days(conn, goal_category(conn, now, goal, kind), today - WEEKS_BACK * WEEK, today + HORIZON_WEEKS * WEEK)
    history = _history(conn, now, goal, kind, off)
    lower = p["unit"] == "min" or (kind == "body" and target < (history[0][1] if history else current))
    created = (goal.get("created_at") or now).astimezone(TZ).date()
    due = deadline(goal.get("text") or "", created, today)
    out = {"goal_id": goal["id"], "text": goal["text"], "kind": kind, "unit": p["unit"], "lower_is_better": lower,
           "target": target, "current": current, "deadline": due.isoformat() if due else None,
           "history": [[d.isoformat(), round(v, 2)] for d, v in history], "projection": [], "eta": None}

    if (current <= target) if lower else (current >= target):
        return {**out, "status": "reached", "summary": f"Reached: {p['label']}."}
    trend = fit(history, today, off)
    if trend is None:
        return {**out, "status": "too_little_data",
                "summary": "A forecast needs about 4 weeks of data with at least 4 sessions or check-ins."}

    flatten = kind != "body"
    proj = project(trend, HORIZON_WEEKS, flatten, off)
    likely, early, late = crossing(proj, target, lower)
    show_until = max(filter(None, [likely and likely + 4 * WEEK, due and due + 2 * WEEK, today + 12 * WEEK]))
    out["projection"] = [[d.isoformat(), round(m, 2), round(lo, 2), round(hi, 2)] for d, m, lo, hi in proj
                         if d <= show_until]
    by = due or today + NEEDED_WITHIN
    weeks_left = max(1.0, (by - today).days / 7)
    needed = (target - current) / weeks_left

    if likely is None:
        within = f"to make {_day_month(due)}" if due else "to get there within 6 months"
        return {**out, "status": "not_at_this_pace",
                "summary": f"Not at this pace: you're at {_rate(trend.per_week, p['unit'])}; "
                           f"you'd need {_rate(needed, p['unit'])} {within}."}
    out["eta"] = {"likely": likely.isoformat(), "early": early.isoformat() if early else None,
                  "late": late.isoformat() if late else None}
    when = month_part(likely, today)
    if due is None:
        return {**out, "status": "eta", "summary": f"Around {when} (likely {_months(early or likely, late, today)})."}
    if likely <= due:
        return {**out, "status": "on_track", "summary": f"On track for {_day_month(due)}: around {when}."}
    return {**out, "status": "behind",
            "summary": f"Behind for {_day_month(due)}: around {when} at this pace. "
                       f"You'd need {_rate(needed, p['unit'])} (now {_rate(trend.per_week, p['unit'])})."}


def goal_forecasts(conn: Connection, now: datetime) -> list[dict]:
    return [f for g in active_goals(conn) if (f := goal_forecast(conn, now, g))]
