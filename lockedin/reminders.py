"""When the next body check-in is due, whether the Hevy upload is stale, and a calendar file for both."""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import Connection, text

HEVY_STALE = timedelta(days=7)


def _settings(conn: Connection) -> tuple[int, bool]:
    row = conn.execute(text("select reminder_weeks, reminder_hevy from profile where id = 1")).one()
    return int(row.reminder_weeks), bool(row.reminder_hevy)


def next_checkin_due(conn: Connection, today: date) -> date:
    last = conn.execute(text("select max(measured_on) from measurements")).scalar()
    weeks, _ = _settings(conn)
    return last + timedelta(weeks=weeks) if last else today


def checkin_due(conn: Connection, today: date) -> bool:
    return next_checkin_due(conn, today) <= today


def hevy_due(conn: Connection, now: datetime) -> tuple[bool, datetime | None]:
    last = conn.execute(text("select max(at) from import_log where source = 'hevy'")).scalar()
    return (last is None or now - last >= HEVY_STALE), last


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line: str) -> list[str]:
    """RFC 5545: lines longer than 75 octets continue on the next line after a single space."""
    out, current = [], ""
    for ch in line:
        limit = 75 if not out else 74  # continuation lines start with a space
        if len((current + ch).encode()) > limit:
            out.append(current)
            current = ch
        else:
            current += ch
    out.append(current)
    return [out[0]] + [" " + part for part in out[1:]]


# Brussels follows EU summer time: last Sunday of March 02:00 → +02:00, last Sunday of October 03:00 → +01:00.
VTIMEZONE = [
    "BEGIN:VTIMEZONE", "TZID:Europe/Brussels",
    "BEGIN:DAYLIGHT", "TZOFFSETFROM:+0100", "TZOFFSETTO:+0200", "TZNAME:CEST", "DTSTART:19700329T020000",
    "RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU", "END:DAYLIGHT",
    "BEGIN:STANDARD", "TZOFFSETFROM:+0200", "TZOFFSETTO:+0100", "TZNAME:CET", "DTSTART:19701025T030000",
    "RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU", "END:STANDARD",
    "END:VTIMEZONE",
]


def calendar_ics(conn: Connection, today: date, app_url: str) -> str:
    weeks, hevy = _settings(conn)
    start = max(next_checkin_due(conn, today), today)
    description = "Fill in your body measurements."
    if hevy:
        description += "\nUpload your latest Hevy export."
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//LockedIn//EN", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
        *VTIMEZONE,
        "BEGIN:VEVENT",
        "UID:lockedin-checkin@lockedin",
        f"DTSTAMP:{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}",
        f"DTSTART;TZID=Europe/Brussels:{start.strftime('%Y%m%d')}T090000",
        "DURATION:PT15M",
        f"RRULE:FREQ=WEEKLY;INTERVAL={weeks}",
        "SUMMARY:LockedIn check-in",
        f"DESCRIPTION:{_escape(description)}",
        f"URL:{app_url.rstrip('/')}/body",
        "BEGIN:VALARM", "ACTION:DISPLAY", "DESCRIPTION:LockedIn check-in", "TRIGGER:PT0M", "END:VALARM",
        "END:VEVENT", "END:VCALENDAR",
    ]
    return "\r\n".join(part for line in lines for part in _fold(line)) + "\r\n"
