"""What actually happened in the activity that ticked an agenda item, compared with the plan."""

from datetime import datetime

from sqlalchemy import Connection, text

from lockedin.agenda.parts import parts
from lockedin.agenda.zwo import ZwiftWorkout
from lockedin.fitness import EstimatedFtp, ftp_at
from lockedin.focus.zones import hr_zone, max_hr_at
from lockedin.routes.activities import downsample

ON_TARGET = 0.03
MAX_POINTS = 600
SMOOTH_S = 30
MIN_COVERAGE = 0.5  # a planned part counts as ridden when the ride covers at least half of it
ACTIVITY = ("id, sport, start_at, duration_s, moving_s, distance_m, avg_power, np, tss, avg_hr, avg_pace_s_per_km, "
            "swim_pace_s_per_100m, swim_lengths, swim_strokes, laps")


def activity(conn: Connection, activity_id: int):
    return conn.execute(text(f"select {ACTIVITY} from activities where id = :i"), {"i": activity_id}).first()


def streams(conn: Connection, activity_id: int, columns: str = "*"):
    return conn.execute(text(f"select {columns} from activity_streams where activity_id = :i"), {"i": activity_id}).first()


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
    smoothed = [_mean(ys[max(0, i - window + 1): i + 1]) for i in range(len(t))]
    thin = downsample({"t_offset": t, "y": smoothed}, MAX_POINTS, ("y",))
    out = []
    for x, m in zip(thin["t_offset"], thin["y"] or []):
        v = transform(m) if transform and m is not None else m
        if v is not None:
            out.append([x, round(v, 1)])
    return out


def zwift_parts(plan_parts: list[dict], s, ftp: float | None) -> tuple[list[dict], bool | None]:
    """Each work part: target vs what was held. A part the ride didn't cover gets no numbers.

    Only an FTP the owner entered is judged against: the estimate (95% of a best 20 min) usually sits below
    Zwift's FTP, so every interval would read "above".
    """
    judge = bool(ftp) and not isinstance(ftp, EstimatedFtp)
    rows = []
    t = list(s.t_offset) if s and s.t_offset else []
    for p in (x for x in plan_parts if x["work"]):
        idx = [i for i, x in enumerate(t) if p["start_s"] <= x < p["end_s"]]
        # By time span, not sample count: a ride recorded every few seconds covers a part as well as one every second.
        covered = max(0, min(p["end_s"], t[-1]) - max(p["start_s"], t[0])) / max(1, p["end_s"] - p["start_s"]) \
            if idx else 0
        target = round((p["from_frac"] + p["to_frac"]) / 2 * ftp) if ftp else None
        avg_w = _mean(s.power[i] for i in idx) if s is not None and s.power and covered >= MIN_COVERAGE else None
        rows.append({
            "label": p["label"], "target_w": target,
            "avg_w": round(avg_w) if avg_w is not None else None,
            "avg_hr": round(h) if avg_w is not None and s.hr and (h := _mean(s.hr[i] for i in idx)) else None,
            "avg_cadence": round(c) if avg_w is not None and s.cadence and (c := _mean(s.cadence[i] for i in idx)) else None,
            # Ridden but no owner FTP to compare with: say nothing rather than "not ridden".
            "status": None if avg_w is None else status(avg_w, target) if target and judge else "no_target",
        })
    if not rows or any(r["status"] in (None, "no_target") for r in rows):
        return rows, None
    return rows, all(r["status"] == "on_target" for r in rows)


MOVING = 0.5  # m/s; slower than this is standing still


def moving_seconds(s) -> list[float]:
    """Moving seconds up to each sample of a stream with a distance."""
    t, d = list(s.t_offset), list(s.distance)
    speed = list(s.speed) if getattr(s, "speed", None) else None
    moving = [0.0]
    for i in range(1, len(t)):
        dt = t[i] - t[i - 1]
        if d[i] is not None and d[i - 1] is not None and dt > 0:
            # Judged on the distance covered in between, so a watch's auto-pause (no samples, then running speed)
            # counts as stopped, and a GPS gap that jumped ahead counts as running.
            still = (d[i] - d[i - 1]) / dt <= MOVING
        else:
            still = speed is not None and (speed[i] or 0) <= MOVING
        moving.append(moving[-1] + (0 if still else dt))
    return moving


def splits(s, band: tuple[int | None, int | None]) -> list[dict] | None:
    """Per-km pace on moving time. A km boundary that falls between two samples (a GPS gap) gets its time
    by interpolation, so a gap spreads over the kms it crossed instead of making one absurd split."""
    if s is None or not s.distance or not any(s.distance):
        return None
    d = list(s.distance)
    moving = moving_seconds(s)
    out: list[dict] = []
    last_m, last_i, k = 0.0, 0, 1

    def split(km: float, at: float, i: int, metres: float) -> dict:
        pace = (at - last_m) / (metres / 1000)
        lo, hi = band
        state = None
        if lo and hi:
            state = "on_target" if lo <= pace <= hi else ("faster" if pace < lo else "slower")
        hr = _mean(s.hr[last_i:i + 1]) if s.hr else None
        return {"km": km, "pace": round(pace), "avg_hr": round(hr) if hr else None, "status": state}

    prev_i = 0
    for i, dist in enumerate(d):
        if dist is None:
            continue
        while dist >= k * 1000:
            d0 = d[prev_i] or 0
            frac = (k * 1000 - d0) / (dist - d0) if dist > d0 else 1
            at = moving[prev_i] + frac * (moving[i] - moving[prev_i])
            out.append(split(k, at, i, 1000))
            last_m, last_i, k = at, i, k + 1
        prev_i = i
    rest = (d[-1] or 0) - (k - 1) * 1000
    if rest >= 200:
        out.append(split(round(k - 1 + rest / 1000, 1), moving[-1], len(d) - 1, rest))
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
    sport = a.sport if item["sport"] == "rest" else item["sport"]  # a rest day ticked by a ride says what the ride was
    if sport == "bike":
        bits = [minutes] + ([f"{a.avg_power} W"] if a.avg_power else [])
        if item.get("zwift"):
            ftp = ftp_at(conn, a.start_at)
            s = streams(conn, a.id, "t_offset, power, null as hr, null as cadence")
            _, on = zwift_parts(parts(ZwiftWorkout(blocks=item["zwift"]["blocks"]), ftp), s, ftp)
            if on:
                bits.append("intervals on target")
    elif sport == "run":
        bits = ([f"{a.distance_m / 1000:.1f} km"] if a.distance_m else [minutes]) + \
            ([f"{_clock(a.avg_pace_s_per_km)}/km"] if a.avg_pace_s_per_km else [])
    elif sport == "swim":
        bits = ([f"{round(a.distance_m)} m"] if a.distance_m else [minutes]) + \
            ([f"{_clock(a.swim_pace_s_per_100m)}/100 m"] if a.swim_pace_s_per_100m else [])
    elif sport == "gym":
        n = conn.execute(text("select count(distinct exercise_id) from gym_sets where workout_id = :i"), {"i": a.id}).scalar()
        bits = [f"{n} exercises", minutes]
    else:
        bits = [minutes]
    return "Done · " + " · ".join(bits)
