"""Everything the session page shows: the plan, and once done, the plan against what was done."""

import re
from datetime import datetime, timedelta

from sqlalchemy import Connection, text

from lockedin.agenda import actual as act
from lockedin.agenda.parts import parts, sweet_spot_minutes, tss_estimate
from lockedin.agenda.store import get_item, local_today
from lockedin.agenda.zwo import ZwiftWorkout, duration_s
from lockedin.fitness import ftp_at
from lockedin.focus.zones import hr_zone_bounds, max_hr_at
from lockedin.plan.build import build_plan
from lockedin.timeutil import TZ


def _saved_plan(conn: Connection, routine: str, day) -> list | None:
    row = conn.execute(text(
        "select items from workout_plans where day = :d and built_on = :b order by id desc limit 1"
    ), {"d": routine, "b": day}).first()
    return row.items if row else None


def _gym_plan(conn: Connection, now: datetime, item: dict, start: datetime | None) -> dict:
    routine = item["routine"]
    if not routine:
        return {"kind": "gym", "routine": None, "items": []}
    day = datetime.fromisoformat(item["day"]).date()
    if start is not None:  # done: what was planned for that day, else the routine as it stood just before
        saved = _saved_plan(conn, routine, day)
        if saved is not None:
            return {"kind": "gym", "routine": routine, "items": saved}
        try:
            built = build_plan(conn, start - timedelta(minutes=1), routine)
        except (LookupError, ValueError):
            return {"kind": "gym", "routine": routine, "items": []}
        return {"kind": "gym", "routine": routine, "items": [i for i in built["items"] if i["kind"] == "routine"]}
    saved = _saved_plan(conn, routine, local_today(now)) if day == local_today(now) else None
    if saved is not None:
        return {"kind": "gym", "routine": routine, "items": saved}
    try:
        return {"kind": "gym", "routine": routine, "items": build_plan(conn, now, routine)["items"]}
    except (LookupError, ValueError):
        return {"kind": "gym", "routine": routine, "items": []}


def _min_reps(reps: str) -> int:
    m = re.match(r"\d+", reps or "")
    return int(m.group()) if m else 0


def _gym_rows(conn: Connection, plan_items: list, activity_id: int) -> list[dict]:
    logged: dict[str, list[dict]] = {}
    for r in conn.execute(text(
        "select e.name, s.weight_kg, s.reps from gym_sets s join exercises e on e.id = s.exercise_id "
        "where s.workout_id = :a and s.set_type <> 'warmup' order by s.exercise_order, s.set_index"
    ), {"a": activity_id}):
        logged.setdefault(r.name, []).append({"kg": r.weight_kg, "reps": r.reps})
    rows = []
    for p in plan_items:
        done = logged.pop(p["exercise"], [])
        planned = {"sets": p["sets"], "reps": p["reps"], "weight_kg": p["weight_kg"], "dumbbell": p.get("dumbbell")}
        if not done:
            state = "skipped_by_you" if p.get("skipped") else "skipped"
        else:
            need_reps, need_kg = _min_reps(p["reps"]), p["weight_kg"]
            good = [s for s in done if (s["reps"] or 0) >= need_reps and (need_kg is None or (s["kg"] or 0) >= need_kg)]
            state = "done" if len(good) >= p["sets"] else "close"
        rows.append({"exercise": p["exercise"], "planned": planned, "done": done, "status": state,
                     "extra": p.get("kind") == "add", "goal": p.get("goal")})
    rows += [{"exercise": name, "planned": None, "done": sets, "status": "added", "extra": False, "goal": None}
             for name, sets in logged.items()]
    return rows


def detail(conn: Connection, now: datetime, item_id: int) -> dict:
    item = get_item(conn, now, item_id)  # LookupError → 404
    a = act.activity(conn, item["activity_id"]) if item["activity_id"] else None
    start = a.start_at if a else None
    ftp = ftp_at(conn, start or now)

    plan: dict = {"kind": "note"}
    if item["sport"] == "bike" and item["zwift"]:
        w = ZwiftWorkout(blocks=item["zwift"]["blocks"])
        ps = parts(w, ftp)
        plan = {"kind": "zwift", "ftp": round(ftp) if ftp else None, "ftp_is_set": bool(conn.execute(text(
                    "select ftp_override from profile where id = 1")).scalar()),
                "parts": ps, "duration_s": duration_s(w), "sweet_spot_min": sweet_spot_minutes(ps), "tss_est": tss_estimate(ps)}
    elif item["sport"] in ("run", "swim"):
        targets = item["targets"] or {}
        max_hr = max_hr_at(conn, start or now)
        zone = targets.get("hr_zone")
        plan = {"kind": "targets", **targets, "hr_bpm": list(hr_zone_bounds(max_hr)[zone]) if zone and max_hr else None}
    elif item["sport"] == "gym":
        plan = _gym_plan(conn, now, item, start)

    actual = None
    if a is not None:
        s = act.streams(conn, a.id)
        actual = {"activity_id": a.id, "start_at": a.start_at.astimezone(TZ).isoformat(), "duration_s": a.duration_s,
                  "moving_s": a.moving_s, "distance_m": a.distance_m, "avg_power": a.avg_power, "np": a.np,
                  "tss": a.tss, "avg_hr": a.avg_hr, "avg_pace_s_per_km": a.avg_pace_s_per_km,
                  "swim_pace_s_per_100m": a.swim_pace_s_per_100m, "swim_lengths": a.swim_lengths,
                  "swim_strokes": a.swim_strokes}
        t = list(s.t_offset) if s is not None and s.t_offset else []
        if item["sport"] == "bike":
            actual["power"] = act.series(t, s.power if s is not None else None)
            actual["hr"] = act.series(t, s.hr if s is not None else None)
            if plan["kind"] == "zwift":
                actual["parts"], actual["intervals_on_target"] = act.zwift_parts(plan["parts"], s, ftp)
        elif item["sport"] == "run":
            actual["pace"] = act.series(t, s.speed if s is not None else None,
                                        transform=lambda v: 1000 / v if v > 0.5 else None)
            actual["hr"] = act.series(t, s.hr if s is not None else None)
            band = ((item["targets"] or {}).get("pace_low"), (item["targets"] or {}).get("pace_high"))
            actual["splits"] = act.splits(s, band)
            actual["zones"] = act.zones(conn, a.start_at, s)
        elif item["sport"] == "gym":
            actual["rows"] = _gym_rows(conn, plan.get("items", []), a.id)
    item["result"] = act.result_line(conn, item) if a is not None else None
    return {"item": item, "plan": plan, "actual": actual}
