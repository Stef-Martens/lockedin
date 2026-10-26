"""A Zwift workout as a timeline of labelled parts, with the planned load."""

from lockedin.agenda.zwo import Intervals, Ramp, Steady, ZwiftWorkout

WORK = 0.75  # average fraction of FTP from which a part counts as work
SWEET_SPOT = (0.84, 0.97)
FREE_RIDE_FRACTION = 0.5


def parts(w: ZwiftWorkout, ftp: float | None) -> list[dict]:
    out: list[dict] = []
    t = 0
    n = 0

    def add(label: str, seconds: int, a: float, b: float, work: bool) -> None:
        nonlocal t
        out.append({"label": label, "start_s": t, "end_s": t + seconds,
                    "from_w": round(a * ftp) if ftp else None, "to_w": round(b * ftp) if ftp else None,
                    "from_frac": a, "to_frac": b, "work": work})
        t += seconds

    for b in w.blocks:
        if isinstance(b, Ramp):
            add("Warm-up" if b.type == "warmup" else "Cool-down", b.duration_s, b.from_power, b.to_power,
                (b.from_power + b.to_power) / 2 >= WORK)
        elif isinstance(b, Steady):
            work = b.power >= WORK
            if work:
                n += 1
            add(f"Interval {n}" if work else "Steady", b.duration_s, b.power, b.power, work)
        elif isinstance(b, Intervals):
            for _ in range(b.repeat):
                n += 1
                add(f"Interval {n}", b.on_s, b.on_power, b.on_power, b.on_power >= WORK)
                add("Recovery", b.off_s, b.off_power, b.off_power, False)
        else:
            add("Free ride", b.duration_s, FREE_RIDE_FRACTION, FREE_RIDE_FRACTION, False)
    return out


def _avg(p: dict) -> float:
    return (p["from_frac"] + p["to_frac"]) / 2


def sweet_spot_minutes(ps: list[dict]) -> int:
    lo, hi = SWEET_SPOT
    return round(sum(p["end_s"] - p["start_s"] for p in ps if lo <= _avg(p) <= hi) / 60)


def tss_estimate(ps: list[dict]) -> int:
    return round(sum((p["end_s"] - p["start_s"]) / 3600 * _avg(p) ** 2 * 100 for p in ps))
