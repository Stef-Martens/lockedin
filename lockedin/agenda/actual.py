"""What actually happened in the activity that ticked an agenda item, compared with the plan."""

import math
from datetime import datetime

from sqlalchemy import Connection, text

from lockedin.agenda.parts import parts
from lockedin.agenda.zwo import ZwiftWorkout
from lockedin.fitness import ftp_at
from lockedin.focus.zones import hr_zone, max_hr_at

ON_TARGET = 0.03
MAX_POINTS = 600
SMOOTH_S = 30
MIN_COVERAGE = 0.5  # a planned part counts as ridden when the ride covers at least half of it
ACTIVITY = ("id, start_at, duration_s, moving_s, distance_m, avg_power, np, tss, avg_hr, avg_pace_s_per_km, "
            "swim_pace_s_per_100m, swim_lengths, swim_strokes")


def activity(conn: Connection, activity_id: int):
    return conn.execute(text(f"select {ACTIVITY} from activities where id = :i"), {"i": activity_id}).first()


def streams(conn: Connection, activity_id: int):
    return conn.execute(text("select * from activity_streams where activity_id = :i"), {"i": activity_id}).first()


def status(actual: float, target: float) -> str:
    if abs(actual - target) <= ON_TARGET * target:
        return "on_target"
    return "above" if actual > target else "below"


def _mean(values) -> float | None:
    vals = [v for v in values if v is not None]
    return sum(vals) / len(vals) if vals else None


def series(t: list[int], ys: list | None, smooth: bool = True, transform=None) -> list[list[float]] | None:
    """[[t, value]] smoothed over ~30 s and thinned to at most 600 points."""
    if not ys or not any(y is not None for y in ys):
        return None
    step = (t[-1] - t[0]) / (len(t) - 1) if len(t) > 1 else 1
    window = max(1, round(SMOOTH_S / step)) if smooth else 1
    size = max(1, math.ceil(len(t) / MAX_POINTS))
    out = []
    for i in range(0, len(t), size):
        m = _mean(ys[max(0, i - window + 1): i + 1])
        if m is not None:
            v = transform(m) if transform else m
            if v is not None:
                out.append([t[i], round(v, 1)])
    return out


def zwift_parts(plan_parts: list[dict], s, ftp: float | None) -> tuple[list[dict], bool | None]:
    """Each work part: target vs what was held. A part the ride didn't cover gets no numbers."""
    rows = []
    t = list(s.t_offset) if s and s.t_offset else []
    for p in (x for x in plan_parts if x["work"]):
        idx = [i for i, x in enumerate(t) if p["start_s"] <= x < p["end_s"]]
        covered = len(idx) / max(1, p["end_s"] - p["start_s"])
        target = round((p["from_frac"] + p["to_frac"]) / 2 * ftp) if ftp else None
        avg_w = _mean(s.power[i] for i in idx) if s is not None and s.power and covered >= MIN_COVERAGE else None
        rows.append({
            "label": p["label"], "target_w": target,
            "avg_w": round(avg_w) if avg_w is not None else None,
            "avg_hr": round(h) if avg_w is not None and s.hr and (h := _mean(s.hr[i] for i in idx)) else None,
            "avg_cadence": round(c) if avg_w is not None and s.cadence and (c := _mean(s.cadence[i] for i in idx)) else None,
            "status": status(avg_w, target) if avg_w is not None and target else None,
        })
    if not rows or any(r["status"] is None for r in rows):
        return rows, None
    return rows, all(r["status"] == "on_target" for r in rows)


def splits(s, band: tuple[int | None, int | None]) -> list[dict] | None:
    if s is None or not s.distance or not any(s.distance):
        return None
    t, d = list(s.t_offset), list(s.distance)
    out, k, last_i = [], 1, 0

    def split(km: float, i: int, metres: float) -> dict:
        pace = (t[i] - t[last_i]) / (metres / 1000)
        lo, hi = band
        state = None
        if lo and hi:
            state = "on_target" if lo <= pace <= hi else ("faster" if pace < lo else "slower")
        hr = _mean(s.hr[last_i:i + 1]) if s.hr else None
        return {"km": km, "pace": round(pace), "avg_hr": round(hr) if hr else None, "status": state}

    for i, dist in enumerate(d):
        if dist is not None and dist >= k * 1000:
            out.append(split(k, i, 1000))
            last_i, k = i, k + 1
    rest = (d[-1] or 0) - (k - 1) * 1000
    if rest >= 200:
        out.append(split(round(k - 1 + rest / 1000, 1), len(d) - 1, rest))
    return out or None


def zones(conn: Connection, start: datetime, s) -> dict | None:
    max_hr = max_hr_at(conn, start)
    if not max_hr or s is None or not s.hr:
        return None
    t = list(s.t_offset)
    out = {str(z): 0 for z in range(1, 6)}
    for i, hr in enumerate(s.hr):
        if hr:
            dt = min(10, (t[i + 1] - t[i]) if i + 1 < len(t) else 1)
            out[str(hr_zone(hr, max_hr))] += dt
    return out


def _clock(seconds: float) -> str:
    seconds = round(seconds)
    return f"{seconds // 60}:{seconds % 60:02d}"


def result_line(conn: Connection, item: dict) -> str | None:
    """One line for a done item: what was done, in the item's own terms."""
    if not item.get("activity_id"):
        return None
    a = activity(conn, item["activity_id"])
    if a is None:
        return None
    minutes = f"{round((a.moving_s or a.duration_s) / 60)}′"
    if item["sport"] == "bike":
        bits = [minutes] + ([f"{a.avg_power} W"] if a.avg_power else [])
        if item.get("zwift"):
            ftp = ftp_at(conn, a.start_at)
            _, on = zwift_parts(parts(ZwiftWorkout(blocks=item["zwift"]["blocks"]), ftp), streams(conn, a.id), ftp)
            if on:
                bits.append("intervals on target")
    elif item["sport"] == "run":
        bits = ([f"{a.distance_m / 1000:.1f} km"] if a.distance_m else [minutes]) + \
            ([f"{_clock(a.avg_pace_s_per_km)}/km"] if a.avg_pace_s_per_km else [])
    elif item["sport"] == "swim":
        bits = ([f"{round(a.distance_m)} m"] if a.distance_m else [minutes]) + \
            ([f"{_clock(a.swim_pace_s_per_100m)}/100 m"] if a.swim_pace_s_per_100m else [])
    elif item["sport"] == "gym":
        n = conn.execute(text("select count(distinct exercise_id) from gym_sets where workout_id = :i"), {"i": a.id}).scalar()
        bits = [f"{n} exercises", minutes]
    else:
        bits = [minutes]
    return "Done · " + " · ".join(bits)
