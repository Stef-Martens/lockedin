"""The owner's training preferences: muscles to leave out, exercises never to suggest, notes for the coach."""

import hashlib
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import Connection, text

from lockedin.timeoff import off_muscles


@dataclass
class Preferences:
    avoid_muscles: list[str] = field(default_factory=list)
    never_exercises: list[str] = field(default_factory=list)
    coach_notes: str = ""
    off_muscles: dict[str, date] = field(default_factory=dict)  # muscle -> the day it is back, from time off


def load_preferences(conn: Connection, on: date | None = None) -> Preferences:
    """With `on`, muscles that time off keeps out that day are in `off_muscles` and also in `avoid_muscles`."""
    row = conn.execute(text("select avoid_muscles, never_exercises, coach_notes from profile where id = 1")).first()
    prefs = Preferences(list(row.avoid_muscles), list(row.never_exercises), row.coach_notes) if row else Preferences()
    if on is not None:
        prefs.off_muscles = off_muscles(conn, on)
        prefs.avoid_muscles += [m for m in prefs.off_muscles if m not in prefs.avoid_muscles]
    return prefs


def prefs_hash(p: Preferences) -> str:
    """Changes whenever what the planner may suggest changes (notes don't affect plans)."""
    key = "|".join(sorted(p.avoid_muscles)) + "#" + "|".join(sorted(p.never_exercises))
    return hashlib.sha1(key.encode()).hexdigest()[:16]
