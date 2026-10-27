"""Race times from training runs, by Riegel's formula: T2 = T1 × (D2 / D1)^1.06."""

import calendar
from datetime import date, datetime, time, timedelta

from sqlalchemy import Connection, text

from lockedin.focus.sessions import counted
from lockedin.timeutil import TZ

DISTANCES = (("5k", 5.0), ("10k", 10.0), ("Half marathon", 21.0975))
RIEGEL = 1.06  # Riegel 1981; holds best between about 1.5 km and the marathon for someone trained for the distance
LOOKBACK = timedelta(days=90)
MIN_KM = 3.0
MIN_SHARE = 0.4  # a half marathon isn't read from a 5k: the run must be at least 40% of the distance
HISTORY_MONTHS = 6
NOTE = ("From training runs, not races, so a race effort is usually a bit faster. Riegel's formula assumes "
        "you've trained for the distance.")


def riegel(seconds: float, km_from: float, km_to: float) -> float:
    return seconds * (km_to / km_from) ** RIEGEL


def _best(runs: list, km: float) -> tuple[float, object] | None:
    """The fastest prediction for `km` from runs long enough to say something about it."""
    options = [(riegel(r.secs, r.km, km), r) for r in runs if r.km >= MIN_SHARE * km]
    return min(options, key=lambda o: o[0]) if options else None


def race_forecast(conn: Connection, now: datetime) -> dict | None:
    since = now - LOOKBACK - timedelta(days=31 * HISTORY_MONTHS)
    runs = conn.execute(text(
        "select a.id, a.start_at, a.distance_m / 1000.0 as km, coalesce(a.moving_s, a.duration_s) as secs "
        f"from activities a where {counted('a')} and a.sport = 'run' and a.distance_m >= :min_m "
        "and coalesce(a.moving_s, a.duration_s) > 0 and a.start_at > :since and a.start_at <= :now order by a.start_at"
    ), {"min_m": MIN_KM * 1000, "since": since, "now": now}).all()
    recent = [r for r in runs if r.start_at > now - LOOKBACK]
    predictions = []
    for name, km in DISTANCES:
        if best := _best(recent, km):
            secs, r = best
            predictions.append({"name": name, "km": km, "seconds": round(secs), "from": {
                "activity_id": r.id, "day": r.start_at.astimezone(TZ).date().isoformat(),
                "km": round(float(r.km), 2), "seconds": round(r.secs)}})
    if not predictions:
        return None
    return {"predictions": predictions, "history": _history(runs, now), "note": NOTE}


def _history(runs: list, now: datetime) -> list[list]:
    """Predicted 5k seconds at the end of each of the last six months, and today."""
    today = now.astimezone(TZ).date()
    points: list[date] = []
    y, m = today.year, today.month
    for _ in range(HISTORY_MONTHS):
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
        points.append(date(y, m, calendar.monthrange(y, m)[1]))
    out = []
    for d in sorted(points) + [today]:
        end = now if d == today else datetime.combine(d + timedelta(days=1), time(), TZ)
        if best := _best([r for r in runs if end - LOOKBACK < r.start_at <= end], 5.0):
            out.append([d.isoformat(), round(best[0])])
    return out
