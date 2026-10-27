"""A trend through weekly values, projected forward with a "likely" band, and when it reaches a target."""

import calendar
import math
import re
from dataclasses import dataclass
from datetime import date, timedelta

WINDOW = timedelta(weeks=12)        # the trend is today's: the last 12 weeks...
WIDE_WINDOW = timedelta(weeks=26)   # ...or 26 when 12 hold too few points
MIN_POINTS = 4
MIN_SPAN = timedelta(days=28)
HALF_LIFE_DAYS = 182  # gains slow down: the weekly gain halves every 6 months (strength, FTP, run times)
HORIZON_WEEKS = 52


@dataclass
class Trend:
    today: date
    at_today: float   # the fitted value today
    per_day: float
    sd: float         # scatter of the weeks around the line
    se_slope: float   # how sure the slope is

    @property
    def per_week(self) -> float:
        return self.per_day * 7


def fit(points: list[tuple[date, float]], today: date) -> Trend | None:
    """Least squares over the last 12 weeks (26 when that's thin); None with under 4 points or 4 weeks."""
    for window in (WINDOW, WIDE_WINDOW):
        pts = [(d, v) for d, v in points if today - window <= d <= today]
        if len(pts) >= MIN_POINTS and max(d for d, _ in pts) - min(d for d, _ in pts) >= MIN_SPAN:
            break
    else:
        return None
    xs = [(d - today).days for d, _ in pts]
    ys = [v for _, v in pts]
    n, mx, my = len(xs), sum(xs) / len(xs), sum(ys) / len(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    at_today = my - slope * mx
    sd = math.sqrt(sum((y - (at_today + slope * x)) ** 2 for x, y in zip(xs, ys)) / (n - 2))
    return Trend(today, at_today, slope, sd, sd / math.sqrt(sxx))


def _days_of_gain(days: float, flatten: bool) -> float:
    """Days' worth of today's weekly gain by `days` from now; with flattening, each week gains a bit less."""
    if not flatten:
        return days
    return HALF_LIFE_DAYS / math.log(2) * (1 - 0.5 ** (days / HALF_LIFE_DAYS))


def project(t: Trend, weeks: int, flatten: bool) -> list[tuple[date, float, float, float]]:
    """(day, likely, low, high) weekly from next week. The band is one standard error either side: the line's own
    uncertainty grows with time, plus the usual week-to-week scatter."""
    out = []
    for k in range(1, weeks + 1):
        g = _days_of_gain(7 * k, flatten)
        mid = t.at_today + t.per_day * g
        spread = math.hypot(t.se_slope * g, t.sd)
        out.append((t.today + timedelta(weeks=k), mid, mid - spread, mid + spread))
    return out


def crossing(proj: list[tuple[date, float, float, float]], target: float,
             lower_is_better: bool) -> tuple[date | None, date | None, date | None]:
    """(likely, early, late): when the likely line, the hopeful edge and the cautious edge reach the target."""
    def first(i: int) -> date | None:
        reached = (lambda v: v <= target) if lower_is_better else (lambda v: v >= target)
        return next((p[0] for p in proj if reached(p[i])), None)
    hopeful, cautious = (2, 3) if lower_is_better else (3, 2)
    return first(1), first(hopeful), first(cautious)


MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_name) if m} | \
    {m.lower(): i for i, m in enumerate(calendar.month_abbr) if m} | \
    {"januari": 1, "februari": 2, "maart": 3, "mei": 5, "juni": 6, "juli": 7, "augustus": 8, "oktober": 10}
_MONTH = "|".join(sorted(MONTHS, key=len, reverse=True))
BY = r"\b(?:by|before|until|tegen|voor|tot)\s+(?:the\s+)?(?:end\s+of\s+|eind\s+)?"
ISO_DATE = re.compile(BY + r"(\d{4})-(\d{2})-(\d{2})\b", re.I)
MONTH_DATE = re.compile(BY + rf"(?:(\d{{1,2}})\s+)?({_MONTH})\b\.?(?:\s+(\d{{4}}))?", re.I)
IN_SPAN = re.compile(r"\b(?:in|within|binnen)\s+(\d{1,2})\s+(weeks?|weken|months?|maanden)\b", re.I)


def deadline(words: str, created: date, today: date) -> date | None:
    """The date a goal names: "by March 2027", "by june" (the next one), "before 15 January", "by 2027-04-01",
    "in 12 weeks" (from when the goal was set). A month alone means its last day."""
    if m := ISO_DATE.search(words):
        return date(int(m[1]), int(m[2]), int(m[3]))
    if m := MONTH_DATE.search(words):
        month = MONTHS[m[2].lower()]
        year = int(m[3]) if m[3] else (today.year if month >= today.month else today.year + 1)
        day = int(m[1]) if m[1] else calendar.monthrange(year, month)[1]
        try:
            return date(year, month, day)
        except ValueError:
            return None
    if m := IN_SPAN.search(words):
        n = int(m[1])
        if m[2].lower().startswith("w"):
            return created + timedelta(weeks=n)
        y, mo = divmod(created.month - 1 + n, 12)
        year, month = created.year + y, mo + 1
        return date(year, month, min(created.day, calendar.monthrange(year, month)[1]))
    return None


def month_part(d: date, today: date) -> str:
    """"early March", "mid-November", "late December 2027" (the year only when it isn't this one)."""
    part = "early " if d.day <= 10 else "mid-" if d.day <= 20 else "late "
    return f"{part}{calendar.month_name[d.month]}{f' {d.year}' if d.year != today.year else ''}"
