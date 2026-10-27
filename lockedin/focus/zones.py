"""Heart-rate zones as % of max HR, power zones as % of FTP (Coggan-style), 5 zones each."""

from datetime import date, datetime, timedelta

from sqlalchemy import Connection, text

from lockedin.fit.metrics import rolling_means
from lockedin.focus.sessions import COUNTED_SQL, counted
from lockedin.timeutil import TZ

# Olympiatoppen intensity scale (Seiler 2010): I1 60–72, I2 72–82, I3 82–87, I4 87–92, I5 > 92 % of max HR,
# with everything below 72 % folded into zone 1. Zones 1–2 sit below the first ventilatory threshold (Seiler's
# zone 1), zone 3 between the thresholds, zones 4–5 above the second (hard).
HR_ZONE_STARTS = (0, 72, 82, 87, 92)          # % of max HR where zones 1..5 start
POWER_ZONE_STARTS = (0, 56, 76, 91, 106)      # % of FTP where zones 1..5 start
PLAUSIBLE_MAX_HR = (140, 215)
MAX_HR_WINDOW_S = 30  # a max HR held 30 s, so one optical spike can't set every zone
HR_MAX_GAP_S = 10


def _zone(value: float, ref: float, starts: tuple[int, ...]) -> int:
    pct100 = value * 100
    zone = 1
    for z, start in enumerate(starts, start=1):
        if pct100 >= start * ref:  # integer-safe "value/ref >= start%"
            zone = z
    return zone


def hr_zone(hr: float, max_hr: float) -> int:
    return _zone(hr, max_hr, HR_ZONE_STARTS)


def power_zone(watts: float, ftp: float) -> int:
    return _zone(watts, ftp, POWER_ZONE_STARTS)


def hr_zone_bounds(max_hr: int) -> dict[int, tuple[int, int]]:
    ends = HR_ZONE_STARTS[1:] + (100,)
    return {z: (round(max_hr * s / 100), round(max_hr * e / 100)) for z, (s, e) in enumerate(zip(HR_ZONE_STARTS, ends), 1)}


def power_zone_bounds(ftp: float) -> dict[int, tuple[int, int | None]]:
    """Zone 5 (VO2max and up) has no ceiling."""
    ends = (55, 75, 90, 105, None)
    return {z: (round(ftp * s / 100), round(ftp * e / 100) if e else None)
            for z, (s, e) in enumerate(zip(POWER_ZONE_STARTS, ends), 1)}


def _age(dob: date, on: date) -> int:
    return on.year - dob.year - ((on.month, on.day) < (dob.month, dob.day))


def _best_30s_hr(conn: Connection, since: datetime, now: datetime) -> float | None:
    """Highest 30-s mean HR in any stream. Sessions go highest max HR first and stop once no session's max
    could beat the best mean so far, so usually only a couple of streams are read."""
    lo, hi = PLAUSIBLE_MAX_HR
    rows = conn.execute(text(
        "select a.id, a.max_hr from activities a join activity_streams s on s.activity_id = a.id "
        f"where {counted('a')} "
        "and a.start_at > :since and a.start_at <= :now and s.hr is not null "
        "order by a.max_hr desc nulls first"
    ), {"since": since, "now": now}).all()
    best = None
    for r in rows:
        if best is not None and r.max_hr is not None and r.max_hr <= best:
            break
        s = conn.execute(text("select t_offset, hr from activity_streams where activity_id = :i"), {"i": r.id}).one()
        hr = [h if h and h <= hi else None for h in s.hr]  # above any human max: sensor noise
        means = rolling_means(hr, s.t_offset, MAX_HR_WINDOW_S, HR_MAX_GAP_S, gap=None)
        if means and (best is None or max(means) > best):
            best = max(means)
    return best if best is not None and best >= lo else None


def max_hr_at(conn: Connection, now: datetime) -> int | None:
    """Override; else the best 30-s HR in the last year's streams; else the 2nd-highest session max
    (one reading can be a spike); else Tanaka's 208 − 0.7 × age."""
    p = conn.execute(text("select max_hr_override, date_of_birth from profile where id = 1")).one()
    if p.max_hr_override:
        return int(p.max_hr_override)
    since = now - timedelta(days=365)
    best = _best_30s_hr(conn, since, now)
    if best:
        return round(best)
    lo, hi = PLAUSIBLE_MAX_HR
    maxes = conn.execute(text(
        f"select max_hr from activities where {COUNTED_SQL} and start_at > :since and start_at <= :now "
        "and max_hr between :lo and :hi order by max_hr desc limit 2"
    ), {"since": since, "now": now, "lo": lo, "hi": hi}).scalars().all()
    if maxes:
        return int(maxes[-1])  # the only one when there's just one
    if p.date_of_birth:
        return round(208 - 0.7 * _age(p.date_of_birth, now.astimezone(TZ).date()))  # Tanaka et al. 2001
    return None
