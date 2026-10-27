from datetime import UTC, datetime, timedelta

from focus_helpers import add_session
from sqlalchemy import text

from lockedin.focus.mix import effort_mix, session_suggestions

NOW = datetime(2026, 10, 26, 9, 0, tzinfo=UTC)


def test_steady_runs_get_intervals_and_a_long_run(conn):
    conn.execute(text("update profile set max_hr_override = 190"))
    for d in (2, 6, 11, 16):
        add_session(conn, "run", NOW - timedelta(days=d), 2700, avg_hr=160, distance_m=7000)  # 84 % → steady
    mix = effort_mix(conn, NOW, "run")
    assert mix.counts["steady"] == 4 and mix.counts["hard"] == 0
    sugg = session_suggestions(conn, NOW)
    assert [s.title for s in sugg] == ["Long easy run", "Intervals"]
    assert sugg[0].detail == "60–75 min in zone 2 (HR 137–156 bpm)"
    assert sugg[1].detail == "6 × 3 min hard (zone 4, HR 165–175 bpm) with 2 min easy jogs"


def test_too_few_runs_no_suggestion(conn):
    add_session(conn, "run", NOW - timedelta(days=5), 2700, avg_hr=148)
    assert session_suggestions(conn, NOW) == []


def test_bike_intervals_use_ftp_watts(conn):
    conn.execute(text("update profile set ftp_override = 250, max_hr_override = 190"))
    for d in (2, 5, 9, 13):
        add_session(conn, "bike", NOW - timedelta(days=d), 3600, source="zwift", power=[200] * 3600)  # 80 % → steady
    titles = {s.title: s.detail for s in session_suggestions(conn, NOW)}
    assert titles["Intervals"] == "4 × 8 min at 91–105% FTP (228–262 W), 4 min easy between"
    assert titles["Long easy ride"] == "90 min in zone 2 (140–188 W)"


def test_mostly_hard_gets_an_easy_session(conn):
    conn.execute(text("update profile set max_hr_override = 190"))
    for d in (2, 6, 11):
        add_session(conn, "run", NOW - timedelta(days=d), 2700, avg_hr=170)  # hard
    add_session(conn, "run", NOW - timedelta(days=14), 5400, avg_hr=125)  # a long one, so "long" isn't missing
    titles = [s.title for s in session_suggestions(conn, NOW)]
    assert "Easy run" in titles and "Intervals" not in titles


def test_unknown_zones_omit_the_numbers(conn):
    for d in (2, 6, 11):
        add_session(conn, "run", NOW - timedelta(days=d), 2700, distance_m=7000)
    sugg = session_suggestions(conn, NOW)
    assert sugg[0].detail == "60–75 min in zone 2"
