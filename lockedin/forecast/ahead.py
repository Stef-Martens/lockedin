"""Fitness, fatigue and form two weeks ahead, if the agenda's sessions are done as planned."""

from datetime import date, datetime, timedelta

from sqlalchemy import Connection, text

from lockedin.agenda.parts import parts, tss_estimate
from lockedin.agenda.steps import expand
from lockedin.agenda.store import items_between
from lockedin.agenda.zwo import ZwiftWorkout
from lockedin.focus.load import GYM_TSS_PER_HOUR, SEED_DAYS, UNMEASURED_IF, _day_start, activity_loads, pmc
from lockedin.focus.sessions import COUNTED_SQL
from lockedin.timeutil import TZ

BACK_DAYS, AHEAD_DAYS = 28, 14
ZONE_IF = {1: 0.55, 2: 0.7, 3: 0.82, 4: 0.92, 5: 1.0}  # intensity a heart-rate zone stands for (zones 72/82/87/92%)
PLANNED_MIN = {"bike": 60, "run": 45, "swim": 45, "gym": 60}  # a session planned without a length


def _mean(low: int | None, high: int | None) -> float | None:
    return (low + high) / 2 if low and high else None


def stepped_load(targets: dict) -> float:
    """A run's load from its steps: each step's time × intensity². Open steps and distance steps with no pace
    to time them add nothing; repeated work at a pace counts as zone 4, recovery as zone 1."""
    summary_pace = _mean(targets.get("pace_low"), targets.get("pace_high"))
    total = 0.0
    for s in expand(targets["steps"]):
        goal, target = s["goal"], s["target"] or {}
        pace = _mean(target.get("pace_low"), target.get("pace_high"))
        if "time_s" in goal:
            seconds = goal["time_s"]
        elif "distance_m" in goal and (pace or summary_pace):
            seconds = goal["distance_m"] / 1000 * (pace or summary_pace)
        else:
            continue
        if target.get("hr_zone"):
            intensity = ZONE_IF[target["hr_zone"]]
        elif s["kind"] == "work" and s["repeated"] and pace:
            intensity = ZONE_IF[4]
        elif s["kind"] == "recovery":
            intensity = ZONE_IF[1]
        else:
            intensity = UNMEASURED_IF
        total += seconds / 3600 * intensity ** 2 * 100
    return total


def planned_load(item: dict) -> float:
    """The load a planned session would add: the workout's own TSS for Zwift, a stepped run's from its steps,
    else time × intensity² by its heart-rate zone (moderate when it has none); gym at the same flat rate as
    logged gym sessions."""
    sport, targets = item["sport"], item["targets"] or {}
    if item["zwift"]:
        return float(tss_estimate(parts(ZwiftWorkout(blocks=item["zwift"]["blocks"]), None)))
    if sport == "gym":
        return GYM_TSS_PER_HOUR * PLANNED_MIN["gym"] / 60
    if sport not in ("bike", "run", "swim"):
        return 0.0
    if sport == "run" and targets.get("steps"):
        return stepped_load(targets)
    seconds = targets.get("duration_s")
    paces = [p for p in (targets.get("pace_low"), targets.get("pace_high")) if p]
    if not seconds and targets.get("distance_m") and paces:
        per = 1000 if sport == "run" else 100  # paces are per km for runs, per 100 m for swims
        seconds = targets["distance_m"] / per * sum(paces) / len(paces)
    seconds = seconds or PLANNED_MIN[sport] * 60
    intensity = ZONE_IF.get(targets.get("hr_zone"), UNMEASURED_IF)
    return seconds / 3600 * intensity ** 2 * 100


def fitness_ahead(conn: Connection, now: datetime) -> dict | None:
    """The last 28 days as trained, then 14 days as planned (optional sessions and ones that clash with time off
    left out); None with no training."""
    if not conn.execute(text(f"select exists (select 1 from activities where {COUNTED_SQL})")).scalar():
        return None
    today = now.astimezone(TZ).date()
    first, last = today - timedelta(days=BACK_DAYS - 1), today + timedelta(days=AHEAD_DAYS)
    seed = first - timedelta(days=SEED_DAYS)
    loads: dict[date, float] = dict(activity_loads(conn, _day_start(seed), now))
    for item in items_between(conn, now, today, last):
        if not item["done"] and not item["optional"] and not item["clash"]:  # nothing from what time off rules out
            day = date.fromisoformat(item["day"])
            loads[day] = loads.get(day, 0.0) + planned_load(item)
    rows = [r for r in pmc(loads, seed, last) if r["day"] >= first]
    return {"days": [{"day": r["day"].isoformat(), **{k: round(float(r[k]), 1) for k in ("fitness", "fatigue", "form")},
                      "planned": r["day"] > today} for r in rows]}
