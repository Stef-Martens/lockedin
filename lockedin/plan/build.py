"""Today's plan: the owner's routine with targets, at most one variety swap and up to two extras."""

import uuid
from datetime import datetime

from sqlalchemy import Connection, text

from lockedin.focus.consistency import comeback, in_comeback
from lockedin.focus.preferences import Preferences, load_preferences, prefs_hash
from lockedin.focus.suggest import goal_first, gym_suggestions, low_muscles, low_reason, weighted_pick
from lockedin.goals.steer import goal_muscles
from lockedin.focus.wins import stalled_exercises
from lockedin.plan.goals import active_goals, goal_for, goal_label, known_exercises
from lockedin.plan.routines import Routine, latest_sets, routine
from lockedin.timeutil import TZ

MAX_SWAPS = 1
MAX_ADDS = 2
MAX_MISSED = 5
TOP_REPS = 12  # the top of 8–12: every set there means it's time to go up
GOAL_READY_ON = 3  # a goal lift moves up once its best 3 top-weight sets reach TOP_REPS
STEP_KG = 2.5
DUMBBELL_STEP_KG = 2.0  # per dumbbell


class NoRoutine(LookupError):
    pass


def _library(conn: Connection, names: list[str]) -> tuple[dict[str, str], dict[str, list[str]], dict[str, list[str]]]:
    """(equipment, primary muscles, secondary muscles) per exercise name, from the library."""
    equipment = dict(conn.execute(text(
        "select name, equipment from library_exercises where name = any(:n)"), {"n": names}).all())
    primary: dict[str, list[str]] = {}
    secondary: dict[str, list[str]] = {}
    for name, muscle, role in conn.execute(text(
        "select exercise_name, muscle_key, role from library_muscles where exercise_name = any(:n) order by muscle_key"
    ), {"n": names}):
        (primary if role == "primary" else secondary).setdefault(name, []).append(muscle)
    return equipment, primary, secondary


def _avoided_exercises(conn: Connection, avoid: list[str]) -> frozenset[str]:
    """Exercises whose primary muscle is left out; the planner never suggests these."""
    if not avoid:
        return frozenset()
    return frozenset(conn.execute(text(
        "select distinct exercise_name from library_muscles where role = 'primary' and muscle_key = any(:a)"
    ), {"a": avoid}).scalars())


def _dumbbell_logging(conn: Connection) -> str:
    return conn.execute(text("select dumbbell_weights from profile where id = 1")).scalar() or "pair"


def _item(**fields) -> dict:
    base = {"id": uuid.uuid4().hex[:10], "exercise": "", "equipment": "other", "kind": "routine", "muscle": None,
            "sets": 3, "reps": "8–12", "weight_kg": None, "dumbbell": None, "change": None, "estimate": False,
            "last": [], "replaces": None, "reason": None, "goal": None, "skipped": False, "suggested": False,
            "tried": [], "lighter_sets": 0, "goal_extra": False}
    return {**base, **fields}


def progression(last_sets: list[tuple[float | None, int | None]], equipment: str, dumbbell_logging: str,
                welcome_back: bool, ready_on: int | None = None) -> dict:
    """Target for the sets at last session's top weight: up a step once every one of them hit 12 reps
    (only the best `ready_on` of them, for a goal lift whose extra set shouldn't hold it back).
    Lighter sets before them (ramping up) are counted separately, so the plan never asks for more heavy sets.
    Sets logged with no reps (left empty in Hevy) don't count."""
    last_sets = [(kg, reps) for kg, reps in last_sets if reps]
    weights = [kg for kg, _ in last_sets if kg]
    top = max(weights) if weights else None
    at_top = [reps or 0 for kg, reps in last_sets if (kg or None) == top]
    judged = sorted(at_top, reverse=True)[:ready_on] if ready_on else at_top
    ready = bool(judged) and all(r >= TOP_REPS for r in judged)
    dumbbell = dumbbell_logging if equipment == "dumbbell" else None
    sets = max(len(at_top), 1)
    lighter = len(last_sets) - len(at_top) if top is not None else 0
    if top is None:  # bodyweight with nothing added: progress by a rep
        best = max(at_top, default=0)
        if welcome_back:
            reps = str(best) if best else "8–12"
            return {"weight_kg": None, "reps": reps, "change": "welcome_back", "dumbbell": None, "sets": sets, "lighter_sets": 0}
        return {"weight_kg": None, "reps": str(best + 1), "change": "up" if ready else "same", "dumbbell": None,
                "sets": sets, "lighter_sets": 0}
    if welcome_back or not ready:
        low = min(at_top)
        # Below the 8–12 range last time: aim for one more rep than the weakest set (same as last time after a break).
        reps = "8–12" if low >= 8 else str(low if welcome_back else low + 1)
        return {"weight_kg": top, "reps": reps, "change": "welcome_back" if welcome_back else "same",
                "dumbbell": dumbbell, "sets": sets, "lighter_sets": lighter}
    step = (2 * DUMBBELL_STEP_KG if dumbbell_logging == "pair" else DUMBBELL_STEP_KG) if equipment == "dumbbell" else STEP_KG
    return {"weight_kg": round(top + step, 2), "reps": "8–12", "change": "up", "dumbbell": dumbbell,
            "sets": sets, "lighter_sets": lighter}


def _routine_item(conn: Connection, now: datetime, name: str, routine_sets: list, equipment: dict, primary: dict,
                  logging: str, back: bool, goals: list[dict], item_id: str | None = None,
                  known: list[str] | None = None) -> dict:
    last_sets = latest_sets(conn, now, name) or routine_sets
    tag = equipment.get(name, "other")
    # A bodyweight move done with added weight (dip belt, dumbbell) progresses like any weighted lift.
    load = "other" if tag == "bodyweight" and any(kg for kg, _ in last_sets) else tag
    fields = {"id": item_id} if item_id else {}
    goal = goal_label(goal_for(name, goals, known))
    return _item(exercise=name, equipment=tag, muscle=(primary.get(name) or [None])[0],
                 last=[{"kg": kg, "reps": reps} for kg, reps in last_sets], goal=goal,
                 **progression(last_sets, load, logging, back, ready_on=GOAL_READY_ON if goal else None), **fields)


def _suggested(p: dict, kind: str, muscle: str, reason: str, replaces: str | None = None) -> dict:
    return _item(exercise=p["exercise"], equipment=p["equipment"], kind=kind, muscle=muscle, sets=p["sets"],
                 reps=p["reps"], weight_kg=p["weight_kg"], dumbbell=p["dumbbell"], estimate=p["estimate"],
                 change="new" if p["estimate"] else None, replaces=replaces, reason=reason, suggested=True)


def _freshness(conn: Connection, now: datetime, prefs: Preferences) -> dict:
    return {"built_on": now.astimezone(TZ).date().isoformat(), "prefs_hash": prefs_hash(prefs)}


def build_plan(conn: Connection, now: datetime, title: str | None) -> dict:
    prefs = load_preferences(conn)
    back = in_comeback(conn, now)
    known = known_exercises(conn)
    goals = active_goals(conn)
    logging = _dumbbell_logging(conn)
    never = frozenset(prefs.never_exercises) | _avoided_exercises(conn, prefs.avoid_muscles)

    if title is None:
        if back:
            raise ValueError("The 'just what I've missed' plan is hidden during a comeback.")
        items = [_item(exercise=s.exercise, kind="missed", muscle=s.muscle_key, sets=s.sets, reps=s.reps,
                       weight_kg=s.weight_kg, dumbbell=s.dumbbell, estimate=s.estimate,
                       change="new" if s.estimate else None, reason=s.reason, suggested=True,
                       goal=goal_label(goal_for(s.exercise, goals, known)))
                 for s in gym_suggestions(conn, now, limit=MAX_MISSED)]
        return {"day": None, "source_activity_id": None, "comeback": False, "items": items,
                **_freshness(conn, now, prefs)}

    found = routine(conn, now, title)
    if found is None:
        raise NoRoutine(f"No routine called {title!r} in the last 60 days.")
    names = [e.name for e in found.exercises]
    equipment, primary, secondary = _library(conn, names)

    items = [_routine_item(conn, now, ex.name, ex.last_sets, equipment, primary, logging, back, goals, known=known)
             for ex in found.exercises]
    for it in items:
        # A goal lift gets one more heavy set, up to 4, so it doesn't creep up as the extra set becomes "last time".
        if it["goal"] and it["change"] in ("up", "same"):
            it["goal_extra"] = True  # one of its sets is the goal's; the session still counts as done without it
            if it["sets"] <= 3:
                it["sets"] += 1
                it["reason"] = f"+1 set for your goal: {it['goal']}"

    if not back:
        in_plan = set(names)
        # Variety: swap the first stuck lift (not one a goal is about) for another exercise for the same muscle.
        stalled = set(stalled_exercises(conn, now))
        for i, it in enumerate(items):
            if len([x for x in items if x["kind"] == "swap"]) >= MAX_SWAPS:
                break
            if it["exercise"] in stalled and it["muscle"] and not it["goal"]:
                p = weighted_pick(conn, it["muscle"], now, logging, never, frozenset(in_plan))
                if p:
                    reason = f"Variety: {it['exercise']} hasn't improved in 6 weeks; same muscle, different angle."
                    items[i] = _suggested(p, "swap", it["muscle"], reason, replaces=it["exercise"])
                    in_plan.add(p["exercise"])

        # Extras: low muscles this day naturally trains but the routine doesn't hit directly.
        regions = dict(conn.execute(text("select key, region from muscles")).all())
        hit = {m for n in names for m in primary.get(n, [])}
        day_regions = {regions[m] for m in hit if m in regions}
        day_muscles = {m for m, r in regions.items() if r in day_regions} | {m for n in names for m in secondary.get(n, [])}
        adds = []
        for c in goal_first(low_muscles(conn, now, prefs.avoid_muscles), goal_muscles(conn, now)):
            if len(adds) >= MAX_ADDS:
                break
            if c.key not in day_muscles or c.key in hit:
                continue
            p = weighted_pick(conn, c.key, now, logging, never, frozenset(in_plan))
            if p:
                adds.append(_suggested(p, "add", c.key, low_reason(c)))
                in_plan.add(p["exercise"])
        items += adds

    for it in items:
        if it["suggested"]:
            it["goal"] = goal_label(goal_for(it["exercise"], goals, known))
    return {"day": title, "source_activity_id": found.activity_id, "comeback": back, "items": items,
            **_freshness(conn, now, prefs)}


def _restore(conn: Connection, now: datetime, plan: dict, it: dict) -> dict:
    """The owner's own routine exercise back in place of a swap-in, with its normal target."""
    found: Routine | None = routine(conn, now, plan["day"]) if plan.get("day") else None
    ex = next((e for e in found.exercises if e.name == it["replaces"]), None) if found else None
    if ex is None:
        raise LookupError("There's no other exercise to swap this for.")
    equipment, primary, _ = _library(conn, [ex.name])
    return _routine_item(conn, now, ex.name, ex.last_sets, equipment, primary, _dumbbell_logging(conn),
                         in_comeback(conn, now), active_goals(conn), item_id=it["id"], known=known_exercises(conn))


def swap_item(conn: Connection, now: datetime, plan: dict, item_id: str) -> dict:
    """The plan with one item replaced by the next exercise for the same muscle (never one already tried).
    Once a swap-in runs out of alternatives, the routine exercise it replaced comes back."""
    items = plan["items"]
    idx = next((i for i, it in enumerate(items) if it["id"] == item_id), None)
    if idx is None:
        raise KeyError(item_id)
    it = items[idx]
    if not it["muscle"]:
        raise LookupError("There's no other exercise to swap this for.")
    prefs = load_preferences(conn)
    never = frozenset(prefs.never_exercises) | _avoided_exercises(conn, prefs.avoid_muscles)
    tried = set(it.get("tried", [])) | {it["exercise"]}
    skip = frozenset({x["exercise"] for x in items} | tried | ({it["replaces"]} if it["replaces"] else set()))
    p = weighted_pick(conn, it["muscle"], now, _dumbbell_logging(conn), never, skip)
    if not p:
        if it["replaces"] and it["kind"] == "swap":
            return {**plan, "items": items[:idx] + [_restore(conn, now, plan, it)] + items[idx + 1:]}
        raise LookupError("There's no other exercise to swap this for.")
    replaces = it["replaces"] or (it["exercise"] if it["kind"] == "routine" else None)
    reason = it["reason"] if it["kind"] in ("add", "missed") else f"Swapped in for {replaces} today."
    new = _suggested(p, it["kind"] if it["kind"] != "routine" else "swap", it["muscle"], reason, replaces)
    new.update(id=it["id"], tried=sorted(tried), goal=goal_label(goal_for(p["exercise"], active_goals(conn), known_exercises(conn))))
    return {**plan, "items": items[:idx] + [new] + items[idx + 1:]}
