from datetime import UTC, date, datetime, timedelta

import pytest
from conftest import owner_headers
from sqlalchemy import text

from lockedin.reminders import calendar_ics, checkin_due, hevy_due, next_checkin_due

H = owner_headers()
TODAY = date(2026, 10, 26)
NOW = datetime(2026, 10, 26, 9, 0, tzinfo=UTC)


def measure(conn, on):
    conn.execute(text("insert into measurements (type_id, measured_on, value) values (1, :d, 78)"), {"d": on})


def test_due_when_no_measurements(conn):
    assert next_checkin_due(conn, TODAY) == TODAY and checkin_due(conn, TODAY)


def test_due_after_interval(conn):
    measure(conn, date(2026, 10, 12))
    assert next_checkin_due(conn, TODAY) == date(2026, 10, 26) and checkin_due(conn, TODAY)
    conn.execute(text("update profile set reminder_weeks = 4"))
    assert next_checkin_due(conn, TODAY) == date(2026, 11, 9) and not checkin_due(conn, TODAY)


def log_hevy(conn, at):
    conn.execute(text("insert into import_log (source, at, summary) values ('hevy', :at, '{}')"), {"at": at})


@pytest.mark.parametrize("days, due", [(None, True), (2, False), (8, True)])
def test_hevy_due(conn, days, due):
    if days is not None:
        log_hevy(conn, NOW - timedelta(days=days))
    assert hevy_due(conn, NOW)[0] is due


def test_calendar_file(conn):
    ics = calendar_ics(conn, TODAY, "https://lockedin.example")
    lines = ics.split("\r\n")
    assert lines[0] == "BEGIN:VCALENDAR" and "END:VCALENDAR" in lines
    assert "RRULE:FREQ=WEEKLY;INTERVAL=2" in lines
    assert "DTSTART;TZID=Europe/Brussels:20261026T090000" in lines
    assert "URL:https://lockedin.example/body" in lines
    assert any(l.startswith("DESCRIPTION:") and "Hevy" in l for l in lines)
    assert "\n" not in ics.replace("\r\n", "")
    conn.execute(text("update profile set reminder_hevy = false, reminder_weeks = 1"))
    ics2 = calendar_ics(conn, TODAY, "https://lockedin.example")
    assert "RRULE:FREQ=WEEKLY;INTERVAL=1" in ics2 and "Hevy" not in ics2


def test_calendar_route(client):
    r = client.get("/api/reminders/calendar.ics", headers=H)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/calendar")
    assert 'filename="lockedin-checkin.ics"' in r.headers["content-disposition"]
    assert "URL:http://testserver/body" in r.text


def test_overview_due_flags(client):
    from lockedin.app import app
    from lockedin.routes.overview import get_now
    app.dependency_overrides[get_now] = lambda: NOW
    o = client.get("/api/overview", headers=H).json()
    assert o["checkin_due"] is True and o["next_checkin_on"] == "2026-10-26"
    assert o["hevy_due"] is True and o["hevy_last_upload_at"] is None and o["measure_due"] is True
