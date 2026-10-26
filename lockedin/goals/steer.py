"""Which muscles and sports the owner's active goals point at, so suggestions can lean toward them."""

from datetime import datetime

from sqlalchemy import Connection, text

from lockedin.goals.progress import goal_lift, logged_lifts
from lockedin.plan.goals import active_goals, goal_label, known_exercises


def goal_muscles(conn: Connection, now: datetime) -> dict[str, list[str]]:
    """muscle key → labels of active goals whose lift trains it (primary or secondary)."""
    out: dict[str, list[str]] = {}
    goals = [g for g in active_goals(conn) if g.get("area") in ("gym", "general")]  # body goals aren't lifts
    if not goals:
        return out
    names, known = logged_lifts(conn, now), known_exercises(conn)
    for g in goals:
        lift = goal_lift(conn, now, g, names, known)
        if not lift:
            continue
        for key in conn.execute(text("select muscle_key from library_muscles where exercise_name = :n"), {"n": lift}).scalars():
            out.setdefault(key, []).append(goal_label(g))
    return out


def sport_goals(conn: Connection) -> dict[str, str]:
    """area → label of the first active goal of that kind (bike, run, swim)."""
    out: dict[str, str] = {}
    for g in active_goals(conn):
        if g.get("area") in ("bike", "run", "swim"):
            out.setdefault(g["area"], goal_label(g))
    return out
