"""Effort mix per sport and concrete run/ride suggestions for what's missing (long, hard or easy)."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import Connection

from lockedin.fitness import ftp_at
from lockedin.focus.effort import Effort, effort_for_window
from lockedin.focus.sessions import counted_sessions
from lockedin.focus.zones import hr_zone_bounds, max_hr_at, power_zone_bounds
from lockedin.goals.steer import sport_goals
from lockedin.timeoff import away_on, off_on
from lockedin.timeutil import TZ

ACTIVE_DAYS = 42
LOOKBACK_DAYS = 21
MAX_SUGGESTIONS = 2
# Easy and long runs, % of max HR: Daniels' E pace is ~65–79%; 78 keeps them inside the effort classifier's easy band.
EASY_RUN_HR = (65, 78)


@dataclass
class EffortMix:
    sport: str
    counts: dict[str, int]
    unclassified: int


@dataclass
class SessionSuggestion:
    sport: str
    kind: Effort
    title: str
    detail: str
    reason: str
    goal: str | None = None  # the active goal this serves, if any


def effort_mix(conn: Connection, now: datetime, sport: str, days: int = 28) -> EffortMix:
    counts = {"easy": 0, "steady": 0, "hard": 0, "long": 0}
    unclassified = 0
    for _, effort in effort_for_window(conn, now, days, sport):
        if effort:
            counts[effort] += 1
        else:
            unclassified += 1
    return EffortMix(sport, counts, unclassified)


def _easy(sport: str, max_hr: int | None, ftp: float | None) -> str:
    """How to ride or run easy: zone 2 power on the bike; on foot a heart-rate band, else the talk test."""
    if sport == "bike":
        return " in zone 2 ({}–{} W)".format(*power_zone_bounds(ftp)[2]) if ftp else " in zone 2"
    if max_hr:
        return f" easy (HR {round(max_hr * EASY_RUN_HR[0] / 100)}–{round(max_hr * EASY_RUN_HR[1] / 100)} bpm)"
    return " easy, at a pace you can talk at"


def _intervals(sport: str, max_hr: int | None, ftp: float | None) -> str:
    if sport == "bike":
        watts = f" ({power_zone_bounds(ftp)[4][0]}–{power_zone_bounds(ftp)[4][1]} W)" if ftp else ""
        return f"4 × 8 min at 91–105% FTP{watts}, 4 min easy between"
    hr = f", HR {hr_zone_bounds(max_hr)[4][0]}–{hr_zone_bounds(max_hr)[4][1]} bpm" if max_hr else ""
    return f"6 × 3 min hard (zone 4{hr}) with 2 min easy jogs"


def session_suggestions(conn: Connection, now: datetime) -> list[SessionSuggestion]:
    day = now.astimezone(TZ).date()
    if away_on(conn, day):
        return []
    off = off_on(conn, day)
    max_hr = max_hr_at(conn, now)
    ftp = ftp_at(conn, now)
    out: list[SessionSuggestion] = []
    for sport in ("run", "bike"):
        if sport in off:
            continue
        if len(counted_sessions(conn, now - timedelta(days=ACTIVE_DAYS), now, sport)) < 2:
            continue
        noun = "run" if sport == "run" else "ride"
        recent = effort_for_window(conn, now, LOOKBACK_DAYS, sport)
        month = [e for _, e in effort_for_window(conn, now, 28, sport) if e]
        if not any(e == "long" for _, e in recent):
            detail = ("60–75 min" if sport == "run" else "90 min") + _easy(sport, max_hr, ftp)
            out.append(SessionSuggestion(sport, "long", f"Long easy {noun}", detail,
                                         f"No long {noun} in the last 3 weeks"))
        classified = [e for _, e in recent if e]
        if len(classified) >= 3 and "hard" not in classified:
            out.append(SessionSuggestion(sport, "hard", "Intervals", _intervals(sport, max_hr, ftp),
                                         f"No hard {noun} in the last 3 weeks"))
        if month and sum(e == "hard" for e in month) / len(month) > 0.5:
            out.append(SessionSuggestion(sport, "easy", f"Easy {noun}", f"45 min{_easy(sport, max_hr, ftp)}",
                                         f"Most of your {noun}s this month were hard"))
    # Goals of a sport always bring a session of that sport, first in line.
    goals = sport_goals(conn)
    for sport, label in goals.items():
        if sport in off:
            continue
        mine = next((s for s in out if s.sport == sport), None)
        if mine is None:
            if sport == "run":
                mine = SessionSuggestion("run", "steady", "Steady run 40′", f"40 min{_easy('run', max_hr, ftp)}",
                                         "A regular steady run builds toward it")
            elif sport == "bike":
                mine = SessionSuggestion("bike", "hard", "Intervals", _intervals("bike", max_hr, ftp),
                                         "Threshold work moves FTP the most")
            else:
                mine = SessionSuggestion("swim", "steady", "Swim 30′ steady", "Continuous, at a pace you can hold",
                                         "Regular swims build toward it")
            out.append(mine)
        mine.goal = label
        mine.reason = f"{mine.reason} · toward: {label}"
    out.sort(key=lambda s: s.goal is None)
    return out[:max(MAX_SUGGESTIONS, len(goals))]
