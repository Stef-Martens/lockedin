"""A run's blocks: the watch's own laps, one per planned step, set against the plan's steps when they line up."""

from lockedin.agenda.steps import expand

KINDS = {"warmup": "warmup", "active": "work", "interval": "work", "recovery": "recovery", "rest": "recovery",
         "cooldown": "cooldown"}


def _pace(lap: dict) -> int | None:
    if lap.get("avg_speed"):
        return round(1000 / lap["avg_speed"])
    if lap.get("timer_s") and lap.get("distance_m"):
        return round(lap["timer_s"] / (lap["distance_m"] / 1000))
    return None


def _in_target(target: dict | None, pace: int | None, avg_hr: int | None, zones: dict) -> bool | None:
    target = target or {}
    if target.get("pace_low") is not None:
        return None if pace is None else target["pace_low"] <= pace <= target["pace_high"]
    bpm = zones.get(target.get("hr_zone"))
    return None if bpm is None or avg_hr is None else bpm[0] <= avg_hr <= bpm[1]


def blocks(laps: list | None, steps: dict | None, zones: dict) -> dict | None:
    """None when no lap has a step index. `follows_plan` when each lap is the kind of the plan's step at its
    position and there are no more laps than steps; only then do rows carry the plan's goal and target and are
    judged against it. `zones` is zone → bpm range; without it a zone target isn't judged."""
    laps = [lap for lap in laps or [] if lap.get("step_index") is not None]
    if not laps:
        return None
    kinds = [KINDS.get(lap.get("intensity"), "work") for lap in laps]
    planned = expand(steps) if steps else []
    follows = bool(planned) and len(laps) <= len(planned) and all(k == p["kind"] for k, p in zip(kinds, planned))
    rows = []
    for i, (lap, kind) in enumerate(zip(laps, kinds)):
        step = planned[i] if follows else None
        pace = _pace(lap)
        avg_hr = round(lap["avg_hr"]) if lap.get("avg_hr") else None
        seconds = lap.get("timer_s") if lap.get("timer_s") is not None else lap.get("elapsed_s")
        rows.append({"kind": kind, "repeat": step["repeat"] if step else None,
                     "seconds": None if seconds is None else round(seconds),
                     "metres": None if lap.get("distance_m") is None else round(lap["distance_m"]),
                     "pace_s_per_km": pace, "avg_hr": avg_hr,
                     "planned_goal": step["goal"] if step else None, "planned_target": step["target"] if step else None,
                     "in_target": _in_target(step["target"], pace, avg_hr, zones) if step else None})
    return {"follows_plan": follows, "rows": rows}
