"""Which coach goal, if any, an exercise works toward."""

import re

from sqlalchemy import Connection, text

# Words too generic to tie a goal to a lift on their own ("Cable Fly" isn't about "cable stuff").
STOP_WORDS = {"cable", "machine", "dumbbell", "barbell", "seated", "standing", "incline", "decline", "lying",
              "single", "smith"}


def base_name(exercise: str) -> str:
    return re.sub(r"\s*\([^)]*\)", "", exercise).strip().lower()


def goal_for(exercise: str, goals: list[dict]) -> dict | None:
    active = [g for g in goals if g.get("status", "active") == "active"]
    for g in active:
        if g.get("exercise") and g["exercise"].lower() == exercise.lower():
            return g
    loose = [g for g in active if not g.get("exercise")]
    base = base_name(exercise)
    for g in loose:
        if base and base in g["text"].lower():
            return g
    first = base.split()[0] if base else ""
    if len(first) >= 4 and first not in STOP_WORDS:
        for g in loose:
            if re.search(rf"\b{re.escape(first)}\b", g["text"].lower()):
                return g
    return None


def active_goals(conn: Connection) -> list[dict]:
    return [dict(r) for r in conn.execute(text(
        "select id, text, target, exercise, status from goals where status = 'active' order by created_at, id"
    )).mappings()]


def goal_label(goal: dict | None) -> str | None:
    if not goal:
        return None
    return f"{goal['text']} ({goal['target']})" if goal.get("target") else goal["text"]
