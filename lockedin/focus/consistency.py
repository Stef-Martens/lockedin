"""Totals, weekly volume, week streak and the "welcome back" state. Weeks are Monday–Sunday in Brussels."""

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from sqlalchemy import Connection

from lockedin.focus.sessions import Session, counted_sessions
from lockedin.timeoff import away_on, entries, off_on
from lockedin.timeutil import TZ, week_start

SPORTS = ("bike", "run", "swim", "gym", "other")
STREAK_MIN_SESSIONS = 2
COMEBACK_DAYS = 7
PROTECTED_DAYS = 4  # a week with this many days of time off can't break the streak
EPOCH = datetime(2000, 1, 1, tzinfo=TZ)


@dataclass
class SportTotals:
    time_s: int = 0
    distance_m: float = 0.0
    sessions: int = 0


@dataclass
class Comeback:
    days_since: int | None
    last_session: Session | None
    suggestion: str
    title: str = "Welcome back"


def _local_midnight(d: date) -> datetime:
    return datetime.combine(d, time.min, tzinfo=TZ)


def _sum(sessions: list[Session]) -> dict[str, SportTotals]:
    out = {s: SportTotals() for s in SPORTS}
    for s in sessions:
        t = out[s.sport]
        t.time_s += s.duration_s
        t.distance_m += s.distance_m or 0
        t.sessions += 1
    return out


def totals(conn: Connection, now: datetime) -> dict[str, dict[str, SportTotals]]:
    week_from = _local_midnight(week_start(now))
    month_from = _local_midnight(now.astimezone(TZ).date().replace(day=1))
    # counted_sessions uses start_at > since; nudge back a microsecond so a session at exactly midnight counts
    return {"week": _sum(counted_sessions(conn, week_from - timedelta(microseconds=1), now)),
            "month": _sum(counted_sessions(conn, month_from - timedelta(microseconds=1), now))}


def weekly_volume(conn: Connection, now: datetime, weeks: int) -> list[dict]:
    this_week = week_start(now)
    starts = [this_week - timedelta(weeks=i) for i in range(weeks - 1, -1, -1)]
    rows = {ws: {"week_start": ws, **{s: 0.0 for s in SPORTS}} for ws in starts}
    for s in counted_sessions(conn, _local_midnight(starts[0]) - timedelta(microseconds=1), now):
        rows[week_start(s.start_at)][s.sport] += s.duration_s / 60
    return [{k: (round(v) if k != "week_start" else v) for k, v in r.items()} for r in rows.values()]


def _protected_weeks(conn: Connection, today: date) -> set[date]:
    """Mondays of the weeks up to today with PROTECTED_DAYS or more days inside any time off."""
    days = Counter()
    for d in {e["start"] + timedelta(days=i) for e in entries(conn)
              for i in range((min(e["end"], today) - e["start"]).days + 1)}:
        days[week_start(_local_midnight(d))] += 1
    return {wk for wk, n in days.items() if n >= PROTECTED_DAYS}


def week_streak(conn: Connection, now: datetime) -> int:
    """Consecutive weeks with enough sessions; a protected week with too few is skipped, not counted."""
    per_week = Counter(week_start(s.start_at) for s in counted_sessions(conn, EPOCH, now))
    protected = _protected_weeks(conn, now.astimezone(TZ).date())
    this_week = week_start(now)
    streak, wk = 0, this_week - timedelta(weeks=1)
    while per_week[wk] >= STREAK_MIN_SESSIONS or wk in protected:
        streak += per_week[wk] >= STREAK_MIN_SESSIONS
        wk -= timedelta(weeks=1)
    return streak + (1 if per_week[this_week] >= STREAK_MIN_SESSIONS else 0)


def in_comeback(conn: Connection, now: datetime) -> bool:
    """Back after a break (7+ days off). Someone with no history at all isn't coming back from anything."""
    c = comeback(conn, now)
    return c is not None and c.days_since is not None


def comeback(conn: Connection, now: datetime) -> Comeback | None:
    """None while away: there's nothing to come back to yet. While something is off, the suggestion stays neutral."""
    today = now.astimezone(TZ).date()
    if away_on(conn, today):
        return None
    recent = counted_sessions(conn, now - timedelta(days=90), now)
    last = recent[-1] if recent else (counted_sessions(conn, EPOCH, now) or [None])[-1]
    days = (now - last.start_at).days if last else None
    if days is not None and days < COMEBACK_DAYS:
        return None
    main = Counter(s.sport for s in recent).most_common(1)
    sport = main[0][0] if main else None
    if sport == "bike":
        text_ = "Ease back in: a 30-minute easy ride, just spinning."
    elif sport == "gym":
        text_ = "Ease back in: a short full-body session, 3 exercises × 3 sets, nothing heavy."
    else:
        text_ = "Ease back in: 30 minutes of something easy you enjoy."
    if off_on(conn, today):
        text_ = "Ease back in with something easy your time off allows."
    title = "Welcome back"
    if last and any(e["reason"] == "vacation" and e["end"] < today
                    for e in entries(conn, last.start_at.astimezone(TZ).date())):
        title = "Back from vacation"
    return Comeback(days, last, text_, title)
