"""A Zwift workout as a timeline of labelled parts, with the planned load."""

from lockedin.agenda.zwo import Intervals, Ramp, Steady, ZwiftWorkout
from lockedin.fit.metrics import normalized_power, training_stress

WORK = 0.75  # average fraction of FTP from which a part counts as work
SWEET_SPOT = (0.84, 0.97)
FREE_RIDE_FRACTION = 0.5  # free ride has no target: assumed an easy spin at 50% FTP, for the drawing and the TSS


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


def target_series(ps: list[dict]) -> list[float]:
    """The planned target at 1 Hz as a fraction of FTP, ramps interpolated second by second."""
    out: list[float] = []
    for p in ps:
        n, a, b = p["end_s"] - p["start_s"], p["from_frac"], p["to_frac"]
        out += [a + (b - a) * (i + 0.5) / n for i in range(n)]
    return out


def tss_estimate(ps: list[dict]) -> int:
    """TSS of riding the plan exactly: NP of the target series (time × fraction² undercounts intervals)."""
    series = target_series(ps)
    np_ = normalized_power(series, range(len(series)))
    return round(training_stress(len(series), np_, 1.0)[1]) if np_ else 0
