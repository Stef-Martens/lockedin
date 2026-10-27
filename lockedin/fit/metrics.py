"""Power metrics from per-second ride data (Coggan definitions)."""

from collections.abc import Sequence

MAX_FILL_GAP_S = 5


def _resample_1hz(power: Sequence[int | None], t_offset: Sequence[int], max_gap_s: int = MAX_FILL_GAP_S,
                  gap: float | None = 0.0) -> list:
    """1 Hz series from possibly sparse samples: short gaps forward-filled, longer gaps `gap` (zero for power)."""
    if not t_offset:
        return []
    pairs = sorted(zip(t_offset, power), key=lambda tp: tp[0])  # real files can have clock jumps
    t_offset = [t for t, _ in pairs]
    out = [gap] * (t_offset[-1] - t_offset[0] + 1)
    t0 = t_offset[0]
    for i, (t, p) in enumerate(pairs):
        if p is None:
            continue
        nxt = t_offset[i + 1] if i + 1 < len(t_offset) else t + 1
        span = nxt - t if nxt - t <= max_gap_s else 1
        for s in range(t - t0, t - t0 + span):
            out[s] = float(p)
    return out


def rolling_means(values: Sequence[int | None], t_offset: Sequence[int], window_s: int = 30,
                  max_gap_s: int = MAX_FILL_GAP_S, gap: float | None = 0.0) -> list[float]:
    """Trailing `window_s` means over the 1 Hz series; with gap=None, windows touching a long gap are left out."""
    series = _resample_1hz(values, t_offset, max_gap_s, gap)
    out: list[float] = []
    run, missing = 0.0, 0
    for i, v in enumerate(series):
        if v is None:
            missing += 1
        else:
            run += v
        if i >= window_s:
            old = series[i - window_s]
            if old is None:
                missing -= 1
            else:
                run -= old
        if i >= window_s - 1 and not missing:
            out.append(run / window_s)
    return out


def normalized_power(power: Sequence[int | None], t_offset: Sequence[int]) -> float | None:
    series = _resample_1hz(power, t_offset)
    if len(series) < 30 or not any(series):
        return None
    window = 30
    run = sum(series[:window])
    fourth = [(run / window) ** 4]
    for i in range(window, len(series)):
        run += series[i] - series[i - window]
        fourth.append((run / window) ** 4)
    return (sum(fourth) / len(fourth)) ** 0.25


def best_avg_power(power: Sequence[int | None], t_offset: Sequence[int], window_s: int) -> float | None:
    series = _resample_1hz(power, t_offset)
    if len(series) < window_s or not any(series):
        return None
    run = best = sum(series[:window_s])
    for i in range(window_s, len(series)):
        run += series[i] - series[i - window_s]
        best = max(best, run)
    return best / window_s


def training_stress(duration_s: int, np_: float, ftp: float) -> tuple[float, float]:
    if_ = np_ / ftp
    return if_, duration_s * np_ * if_ / (ftp * 3600) * 100
