from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Brussels")


def week_start(dt: datetime) -> date:
    """Monday of the Brussels-local week that contains `dt` (an aware datetime)."""
    local = dt.astimezone(TZ).date()
    return local - timedelta(days=local.weekday())


def parse_local(s: str, formats: Sequence[str]) -> datetime:
    """Parse a naive Brussels-local string into an aware UTC datetime.

    Ambiguous times (DST end) resolve to the first occurrence; times inside the
    DST-start gap resolve with the pre-transition offset, i.e. shifted forward.
    """
    s = s.strip()
    for fmt in formats:
        try:
            naive = datetime.strptime(s, fmt)
        except ValueError:
            continue
        return naive.replace(tzinfo=TZ, fold=0).astimezone(UTC)
    raise ValueError(f"Unrecognised date: {s!r}")
