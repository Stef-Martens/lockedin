"""Heart-rate zones as % of max HR, power zones as % of FTP (Coggan-style), 5 zones each."""

from datetime import date, datetime, timedelta

from sqlalchemy import Connection, text

from lockedin.focus.sessions import COUNTED_SQL
from lockedin.timeutil import TZ

HR_ZONE_STARTS = (0, 60, 70, 80, 90)          # % of max HR where zones 1..5 start
POWER_ZONE_STARTS = (0, 56, 76, 91, 106)      # % of FTP where zones 1..5 start
PLAUSIBLE_MAX_HR = (140, 215)


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


def power_zone_bounds(ftp: float) -> dict[int, tuple[int, int]]:
    ends = (55, 75, 90, 105, 150)
    return {z: (round(ftp * s / 100), round(ftp * e / 100)) for z, (s, e) in enumerate(zip(POWER_ZONE_STARTS, ends), 1)}


def _age(dob: date, on: date) -> int:
    return on.year - dob.year - ((on.month, on.day) < (dob.month, dob.day))


def max_hr_at(conn: Connection, now: datetime) -> int | None:
    """Override, else highest plausible max HR seen in the last year, else 220 − age."""
    p = conn.execute(text("select max_hr_override, date_of_birth from profile where id = 1")).one()
    if p.max_hr_override:
        return int(p.max_hr_override)
    lo, hi = PLAUSIBLE_MAX_HR
    seen = conn.execute(text(
        f"select max(max_hr) from activities where {COUNTED_SQL} and start_at > :since and start_at <= :now "
        "and max_hr between :lo and :hi"
    ), {"since": now - timedelta(days=365), "now": now, "lo": lo, "hi": hi}).scalar()
    if seen:
        return int(seen)
    if p.date_of_birth:
        return 220 - _age(p.date_of_birth, now.astimezone(TZ).date())
    return None
