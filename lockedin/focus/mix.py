"""Effort mix per sport and concrete run/ride suggestions for what's missing (long, hard or easy)."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import Connection

from lockedin.fitness import ftp_at
from lockedin.focus.effort import Effort, effort_for_window
from lockedin.focus.sessions import counted_sessions
from lockedin.focus.zones import hr_zone_bounds, max_hr_at, power_zone_bounds

ACTIVE_DAYS = 42
LOOKBACK_DAYS = 21
MAX_SUGGESTIONS = 2


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


def effort_mix(conn: Connection, now: datetime, sport: str, days: int = 28) -> EffortMix:
    counts = {"easy": 0, "steady": 0, "hard": 0, "long": 0}
    unclassified = 0
    for _, effort in effort_for_window(conn, now, days, sport):
        if effort:
            counts[effort] += 1
        else:
            unclassified += 1
    return EffortMix(sport, counts, unclassified)


def _zone2(sport: str, max_hr: int | None, ftp: float | None) -> str:
    if sport == "bike" and ftp:
        lo, hi = power_zone_bounds(ftp)[2]
        return f" ({lo}–{hi} W)"
    if sport == "run" and max_hr:
        lo, hi = hr_zone_bounds(max_hr)[2]
        return f" (HR {lo}–{hi} bpm)"
    return ""


def _intervals(sport: str, max_hr: int | None, ftp: float | None) -> str:
    if sport == "bike":
        watts = f" ({power_zone_bounds(ftp)[4][0]}–{power_zone_bounds(ftp)[4][1]} W)" if ftp else ""
        return f"4 × 8 min at 91–105% FTP{watts}, 4 min easy between"
    hr = f", HR {hr_zone_bounds(max_hr)[4][0]}–{hr_zone_bounds(max_hr)[4][1]} bpm" if max_hr else ""
    return f"6 × 3 min hard (zone 4{hr}) with 2 min easy jogs"


def session_suggestions(conn: Connection, now: datetime) -> list[SessionSuggestion]:
    max_hr = max_hr_at(conn, now)
    ftp = ftp_at(conn, now)
    out: list[SessionSuggestion] = []
    for sport in ("run", "bike"):
        if len(counted_sessions(conn, now - timedelta(days=ACTIVE_DAYS), now, sport)) < 2:
            continue
        noun = "run" if sport == "run" else "ride"
        recent = effort_for_window(conn, now, LOOKBACK_DAYS, sport)
        month = [e for _, e in effort_for_window(conn, now, 28, sport) if e]
        if not any(e == "long" for _, e in recent):
            detail = ("60–75 min" if sport == "run" else "90 min") + f" in zone 2{_zone2(sport, max_hr, ftp)}"
            out.append(SessionSuggestion(sport, "long", f"Long easy {noun}", detail,
                                         f"No long {noun} in the last 3 weeks"))
        classified = [e for _, e in recent if e]
        if len(classified) >= 3 and "hard" not in classified:
            out.append(SessionSuggestion(sport, "hard", "Intervals", _intervals(sport, max_hr, ftp),
                                         f"No hard {noun} in the last 3 weeks"))
        if month and sum(e == "hard" for e in month) / len(month) > 0.5:
            out.append(SessionSuggestion(sport, "easy", f"Easy {noun}", f"45 min in zone 2{_zone2(sport, max_hr, ftp)}",
                                         f"Most of your {noun}s this month were hard"))
    return out[:MAX_SUGGESTIONS]
