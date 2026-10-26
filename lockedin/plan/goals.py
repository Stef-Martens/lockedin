"""Which coach goal, if any, an exercise works toward."""

import re

from sqlalchemy import Connection, text

# Words too generic to tie a goal to a lift on their own ("Cable Fly" isn't about "cable stuff").
STOP_WORDS = {"cable", "machine", "dumbbell", "barbell", "seated", "standing", "incline", "decline", "lying",
              "single", "smith"}


def base_name(exercise: str) -> str:
    return re.sub(r"\s*\([^)]*\)", "", exercise).strip().lower()


def _words(phrase: str, text: str) -> bool:
    return bool(re.search(rf"\b{re.escape(phrase)}\b", text))


def goal_for(exercise: str, goals: list[dict], known: list[str] | None = None) -> dict | None:
    """The active goal an exercise works toward. `known` (all exercise names) stops "incline bench press 40 kg"
    from tying to plain bench press: a longer exercise name in the goal's words wins."""
    active = [g for g in goals if g.get("status", "active") == "active"]
    for g in active:
        if g.get("exercise") and g["exercise"].lower() == exercise.lower():
            return g
    base = base_name(exercise)
    longer = [b for b in {base_name(k) for k in known or []} if b != base and base and _words(base, b)]

    def about_a_longer_lift(text: str, word: str) -> bool:
        return any(_words(b, text) for b in longer if _words(word, b))

    loose = [g for g in active if not g.get("exercise")]
    for g in loose:
        text = g["text"].lower()
        if base and _words(base, text) and not about_a_longer_lift(text, base):
            return g
    first = base.split()[0] if base else ""
    if len(first) >= 4 and first not in STOP_WORDS:
        for g in loose:
            text = g["text"].lower()
            if _words(first, text) and not about_a_longer_lift(text, first):
                return g
    return None


def known_exercises(conn: Connection) -> list[str]:
    return list(conn.execute(text("select name from library_exercises union select name from exercises")).scalars())


def active_goals(conn: Connection) -> list[dict]:
    return [dict(r) for r in conn.execute(text(
        "select id, text, target, exercise, status, area, created_at from goals where status = 'active' order by created_at, id"
    )).mappings()]


def goal_label(goal: dict | None) -> str | None:
    if not goal:
        return None
    return f"{goal['text']} ({goal['target']})" if goal.get("target") else goal["text"]
