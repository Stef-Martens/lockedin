"""What the model is told about a workout: the server's facts as JSON, never a raw chart series."""

from bisect import bisect_left
from datetime import UTC, datetime
from itertools import accumulate

from fastapi.encoders import jsonable_encoder
from sqlalchemy import Connection

from lockedin.agenda import actual as act
from lockedin.agenda.detail import _easy_back, detail
from lockedin.agenda.steps import expand
from lockedin.focus.sessions import counted_sessions
from lockedin.focus.zones import hr_ranges
from lockedin.plan.goals import active_goals
from lockedin.routes.activities import gym_sets
from lockedin.timeutil import TZ
from lockedin.verdict.store import is_plan, ticking_item

MATCHED_BY = "the plan's order and lengths from the start of the run"
COMPARISON = ("parts", "intervals_on_target", "splits", "zones", "rows")
RECENT = 3
MIN_COVERED = 0.9  # of the planned time and of the planned distance; less and the run didn't follow the steps
MAX_GAP_S = 30  # moving seconds without a distance reading; more and the steps around it can't be placed exactly
MAX_SPEED = 10  # m/s; metres gained faster than this over moving time were run while the timeline counted a stop
JUMP_SLACK_M = 30  # GPS drift that a stop or an auto-pause can add on its own
MAX_STOP_S = 30  # stopped with samples coming in; the watch may count a time step through it, and this much barely moves a block's average
SAMPLES_EVERY_S = 10  # a longer wait for the next sample means recording stopped (auto-pause), which the watch's clock also does
EVER = datetime(2000, 1, 1, tzinfo=UTC)


def _is_open(step: dict) -> bool:
    return step["goal"].get("time_s") is None and step["goal"].get("distance_m") is None


def _at(xs: list[float], ys: list[float], x: float) -> float | None:
    """y where the rising xs first reach x, between samples by interpolation; None past the end."""
    i = bisect_left(xs, x)
    if i == len(xs):
        return None
    if i == 0 or xs[i] == x:
        return ys[i]
    return ys[i - 1] + (x - xs[i - 1]) / (xs[i] - xs[i - 1]) * (ys[i] - ys[i - 1])


def _avg_hr(hr: list | None, moving: list[float], start: float, end: float) -> int | None:
    """Over the seconds actually moved in the window, so standing at a crossing doesn't lower it."""
    if not hr:
        return None
    vals = [hr[i] for i in range(1, len(moving))
            if hr[i] and moving[i] > moving[i - 1] and start < moving[i] <= end]
    return round(sum(vals) / len(vals)) if vals else None


def _in_target(target: dict | None, pace: int | None, avg_hr: int | None, zones: dict) -> bool | None:
    target = target or {}
    if target.get("pace_low") is not None:
        return None if pace is None else target["pace_low"] <= pace <= target["pace_high"]
    bpm = zones.get(target.get("hr_zone"))
    return None if bpm is None or avg_hr is None else bpm[0] <= avg_hr <= bpm[1]


def _stopped_with_samples(t: list[int], moving: list[float], end: float) -> int:
    """Seconds standing still before `end` while samples kept coming in."""
    return sum(t[i] - t[i - 1] for i in range(1, len(moving))
               if moving[i] == moving[i - 1] and moving[i] < end and t[i] - t[i - 1] <= SAMPLES_EVERY_S)


def step_results(steps: dict, stream, zones: dict[int, tuple[int, int]] | None = None) -> list[dict] | None:
    """Each planned step before the first open one, placed by the plan's order and lengths on the moving-time
    timeline, since the watch moves on by itself. None when that can't be trusted: no time or distance goals, a run
    that didn't cover them, a long GPS gap, metres that jump ahead, or a long stop before a time goal's end. `zones`
    is zone → bpm range; without it a zone target isn't judged."""
    if stream is None or not stream.t_offset or not stream.distance or not any(stream.distance):
        return None
    planned = []
    for step in expand(steps):
        if _is_open(step):
            break
        planned.append(step)
    if not planned:
        return None

    moving = act.moving_seconds(stream)
    if any(b < a for a, b in zip(moving, moving[1:])):  # the clock jumped back
        return None
    known = [i for i, x in enumerate(stream.distance) if x is not None]
    secs = [moving[i] for i in known]
    metres = list(accumulate((stream.distance[i] for i in known), max))
    if secs[0] > 0:  # no reading yet when the run started, at nought metres
        secs, metres = [0.0, *secs], [0.0, *metres]

    rows = []
    start_s, start_m = secs[0], metres[0]
    done = {"time_s": 0.0, "distance_m": 0.0}
    for step in planned:
        goal = step["goal"]
        key = "time_s" if goal.get("time_s") is not None else "distance_m"
        if key == "time_s":
            end_s, end_m = start_s + goal[key], _at(secs, metres, start_s + goal[key])
        else:
            end_s, end_m = _at(metres, secs, start_m + goal[key]), start_m + goal[key]
        if end_s is None or end_m is None:  # the run ended inside this step
            end_s, end_m = secs[-1], metres[-1]
        seconds, covered = end_s - start_s, end_m - start_m
        did = seconds if key == "time_s" else covered
        done[key] += did
        if did >= act.MIN_COVERAGE * goal[key]:
            pace = round(seconds / (covered / 1000)) if covered > 0 and seconds > 0 else None
            avg_hr = _avg_hr(stream.hr, moving, start_s, end_s)
            rows.append({"kind": step["kind"], "repeat": step["repeat"], "goal": goal, "target": step["target"],
                         "seconds": round(seconds), "metres": round(covered), "pace_s_per_km": pace, "avg_hr": avg_hr,
                         "in_target": _in_target(step["target"], pace, avg_hr, zones or {})})
        start_s, start_m = end_s, end_m

    for key, total in done.items():
        if total < MIN_COVERED * sum(s["goal"].get(key) or 0 for s in planned):
            return None
    if any(b - a > MAX_GAP_S and a < start_s for a, b in zip(secs, secs[1:])):
        return None
    if any(m1 - m0 > MAX_SPEED * (s1 - s0) + JUMP_SLACK_M and m0 < start_m
           for s0, s1, m0, m1 in zip(secs, secs[1:], metres, metres[1:])):
        return None
    if done["time_s"] > 0 and _stopped_with_samples(stream.t_offset, moving, start_s) > MAX_STOP_S:
        return None
    return rows or None


def _plan(d: dict, zones: dict) -> dict:
    item, plan = d["item"], dict(d["plan"])
    if item["sport"] == "run" and zones:
        plan["zone_bpm"] = {str(z): list(bpm) for z, bpm in zones.items()}
        if plan.get("hr_bpm"):
            plan["hr_bpm"] = list(zones[plan["hr_zone"]])
    return {"title": item["title"], "note": item["note"], "optional": item["optional"], **plan}


def _planned_comparison(d: dict) -> dict:
    out = {k: d["actual"][k] for k in COMPARISON if k in d["actual"]}
    if out.get("splits") and (d["item"]["targets"] or {}).get("steps"):
        # The summary pace is the work steps' only; a whole km of warm-up or jog isn't "slower" than it.
        out["splits"] = [{k: v for k, v in s.items() if k != "status"} for s in out["splits"]]
    return out


def _own_comparison(conn: Connection, a, s) -> dict:
    if a.sport == "run":
        return {"splits": act.splits(s, (None, None)), "zones": act.zones(conn, a.start_at, s)}
    if a.sport == "gym":
        return {"sets": gym_sets(conn, a.id)}
    return {}


def _recent(conn: Connection, a) -> list[dict]:
    earlier = [s for s in counted_sessions(conn, EVER, a.start_at, a.sport) if s.start_at < a.start_at]
    return [{"date": s.start_at.astimezone(TZ).date().isoformat(), "duration_s": s.duration_s,
             "distance_m": s.distance_m, "avg_hr": s.avg_hr, "avg_power": s.avg_power, "np": s.np,
             "avg_pace_s_per_km": s.avg_pace_s_per_km, "swim_pace_s_per_100m": s.swim_pace_s_per_100m}
            for s in reversed(earlier[-RECENT:])]


def facts(conn: Connection, now: datetime, activity_id: int) -> dict:
    a = act.activity(conn, activity_id)
    if a is None:
        raise LookupError(f"There's no activity {activity_id}.")
    item = ticking_item(conn, now, a)
    day = a.start_at.astimezone(TZ).date().isoformat()
    s = act.streams(conn, a.id, "t_offset, speed, hr, distance") if a.sport == "run" else None
    zones = hr_ranges(conn, a.start_at) if a.sport == "run" else {}

    plan, results = None, None
    if is_plan(item):
        d = detail(conn, now, item["id"])
        plan, comparison, easy_back = _plan(d, zones), _planned_comparison(d), d["easy_back"]
        if a.sport == "run" and (steps := (item["targets"] or {}).get("steps")):
            results = step_results(steps, s, zones)
    else:
        comparison = _own_comparison(conn, a, s)
        easy_back = _easy_back(conn, {"sport": a.sport, "day": day})

    return jsonable_encoder({
        "workout": {**{k: v for k, v in a._mapping.items() if k != "id"}, "start_at": a.start_at.astimezone(TZ)},
        "plan": plan,
        "rest_day": item is not None and not is_plan(item),
        "comparison": comparison,
        "step_results": results,
        "matched_by": MATCHED_BY if results else None,
        "recent": _recent(conn, a),
        "easy_back": easy_back,
        "goals": [g["text"] for g in active_goals(conn)],
    })
