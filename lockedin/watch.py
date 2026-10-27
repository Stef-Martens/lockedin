"""The watch feed: the coming week's runs and swims, shaped for the iPhone app to hand to WorkoutKit."""

from datetime import datetime, timedelta

from sqlalchemy import Connection

from lockedin.agenda.steps import summary_line
from lockedin.agenda.store import items_between, local_today
from lockedin.focus.zones import hr_zone_bounds, max_hr_at

DAYS_AHEAD = 7
ZONE_1_FLOOR = 0.60  # LockedIn's zone 1 starts at 0; on the watch it starts at 60 % of max HR


def _hr_ranges(conn: Connection, now: datetime) -> dict[int, tuple[int, int]]:
    """Zone → bpm range, or empty when max HR isn't known (then heart-rate alerts are left out)."""
    max_hr = max_hr_at(conn, now)
    if max_hr is None:
        return {}
    zones = hr_zone_bounds(max_hr)
    zones[1] = (round(max_hr * ZONE_1_FLOOR), zones[1][1])
    return zones


def _goal(goal: dict) -> dict:
    if goal.get("time_s") is not None:
        return {"type": "time", "seconds": goal["time_s"]}
    if goal.get("distance_m") is not None:
        return {"type": "distance", "meters": goal["distance_m"]}
    return {"type": "open"}


def _alert(target: dict | None, zones: dict[int, tuple[int, int]]) -> dict | None:
    """A pace range as speed in m/s, else a heart-rate zone as bpm, else none."""
    target = target or {}
    if target.get("pace_low") is not None and target.get("pace_high") is not None:
        return {"type": "speed", "min_mps": round(1000 / target["pace_high"], 3),
                "max_mps": round(1000 / target["pace_low"], 3)}
    if (zone := zones.get(target.get("hr_zone"))) is not None:
        return {"type": "heart_rate", "min_bpm": zone[0], "max_bpm": zone[1]}
    return None


def _step(step: dict | None, zones: dict) -> dict | None:
    return {"goal": _goal(step["goal"]), "alert": _alert(step.get("target"), zones)} if step else None


def _summary_goal(targets: dict) -> dict:
    """A run or swim without steps ends after its distance, else its duration, else when stopped."""
    if targets.get("distance_m") is not None:
        return {"distance_m": targets["distance_m"]}
    return {"time_s": targets.get("duration_s")}


def _run(item: dict, zones: dict) -> dict:
    targets = item["targets"] or {}
    steps = targets.get("steps") or {
        "blocks": [{"repeat": 1, "steps": [{"kind": "work", "goal": _summary_goal(targets), "target": targets}]}]}
    blocks = [{"iterations": b["repeat"],
               "steps": [{"purpose": s["kind"], **_step(s, zones)} for s in b["steps"]]} for b in steps["blocks"]]
    return {"kind": "run", "display_name": item["title"], "location": "outdoor", "warmup": _step(steps.get("warmup"), zones),
            "blocks": blocks, "cooldown": _step(steps.get("cooldown"), zones)}


def _swim(item: dict) -> dict:
    return {"kind": "swim", "display_name": item["title"], "location": "pool",
            "goal": _goal(_summary_goal(item["targets"] or {}))}


def feed(conn: Connection, now: datetime) -> dict:
    """Runs and swims from today through a week ahead that aren't done and aren't ruled out by time off."""
    today = local_today(now)
    items = [i for i in items_between(conn, now, today, today + timedelta(days=DAYS_AHEAD))
             if i["sport"] in ("run", "swim") and not i["done"] and not i["clash"]]
    zones = _hr_ranges(conn, now) if any(i["sport"] == "run" for i in items) else {}
    return {"today": today.isoformat(), "items": [
        {"id": i["id"], "day": i["day"], "sport": i["sport"], "title": i["title"], "optional": i["optional"],
         "note": i["note"], "summary": summary_line(i["sport"], i["targets"]),
         "workout": _run(i, zones) if i["sport"] == "run" else _swim(i)} for i in items]}
