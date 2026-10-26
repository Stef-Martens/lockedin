"""The owner's training preferences: muscles to leave out, exercises never to suggest, notes for the coach."""

import hashlib
from dataclasses import dataclass, field

from sqlalchemy import Connection, text


@dataclass
class Preferences:
    avoid_muscles: list[str] = field(default_factory=list)
    never_exercises: list[str] = field(default_factory=list)
    coach_notes: str = ""


def load_preferences(conn: Connection) -> Preferences:
    row = conn.execute(text("select avoid_muscles, never_exercises, coach_notes from profile where id = 1")).first()
    return Preferences(list(row.avoid_muscles), list(row.never_exercises), row.coach_notes) if row else Preferences()


def prefs_hash(p: Preferences) -> str:
    """Changes whenever what the planner may suggest changes (notes don't affect plans)."""
    key = "|".join(sorted(p.avoid_muscles)) + "#" + "|".join(sorted(p.never_exercises))
    return hashlib.sha1(key.encode()).hexdigest()[:16]
