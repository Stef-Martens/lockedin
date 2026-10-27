from datetime import UTC, date, datetime, timedelta

import pytest
from conftest import owner_headers
from focus_helpers import add_session

from lockedin import timeoff
from lockedin.app import app
from lockedin.focus.consistency import comeback, week_streak
from lockedin.routes.overview import get_now
from lockedin.timeoff import Restriction, TimeOffIn

H = owner_headers()
NOW = datetime(2026, 10, 26, 9, 0, tzinfo=UTC)  # Monday 10:00 in Brussels


@pytest.fixture
def at(request):
    def go(now):
        app.dependency_overrides[get_now] = lambda: now
    yield go
    app.dependency_overrides.pop(get_now, None)


def make(conn, reason="injury", label="Knee operation", start=date(2026, 10, 1), **until):
    return timeoff.create(conn, TimeOffIn(reason=reason, label=label, start=start, restrictions=[
        Restriction(category=c, until=u) for c, u in until.items()]))


def two_in_week(conn, weeks_back):
    monday = datetime(2026, 10, 26, 8, 0, tzinfo=UTC) - timedelta(weeks=weeks_back)
    add_session(conn, "run", monday + timedelta(days=1), 1800)
    add_session(conn, "run", monday + timedelta(days=3), 1800)


def test_protected_empty_week_is_skipped_not_broken(conn):
    for w in (2, 3, 4):
        two_in_week(conn, w)
    make(conn, "vacation", None, start=date(2026, 10, 19), all=date(2026, 10, 25))  # all of last week
    add_session(conn, "run", NOW - timedelta(hours=3), 1800)
    add_session(conn, "bike", NOW - timedelta(hours=1), 1800)
    assert week_streak(conn, NOW) == 4


def test_protected_week_with_two_sessions_counts(conn):
    two_in_week(conn, 1)
    two_in_week(conn, 2)
    make(conn, "vacation", None, start=date(2026, 10, 19), all=date(2026, 10, 25))
    assert week_streak(conn, NOW) == 2


def test_four_days_protect_a_week_three_do_not(conn):
    two_in_week(conn, 2)
    make(conn, start=date(2026, 10, 22), run=date(2026, 10, 25))  # Thu-Sun: 4 days of last week
    assert week_streak(conn, NOW) == 1
    make(conn, start=date(2026, 10, 12), run=date(2026, 10, 14))  # 3 days of the week before: no help
    assert week_streak(conn, NOW) == 1


def test_unprotected_empty_week_still_breaks(conn):
    for w in (2, 3):
        two_in_week(conn, w)
    make(conn, "vacation", None, start=date(2026, 10, 22), all=date(2026, 10, 24))  # 3 days only
    assert week_streak(conn, NOW) == 0


def test_vacation_titles_the_comeback(conn):
    add_session(conn, "bike", NOW - timedelta(days=12), 3600)
    make(conn, "vacation", None, start=date(2026, 10, 15), all=date(2026, 10, 22))
    assert comeback(conn, NOW).title == "Back from vacation"


def test_comeback_without_vacation_keeps_generic_title(conn):
    add_session(conn, "bike", NOW - timedelta(days=12), 3600)
    make(conn, start=date(2026, 10, 15), run=date(2026, 10, 22))
    assert comeback(conn, NOW).title == "Welcome back"


def test_time_off_today_text(client, clean_db, at):
    at(NOW)
    assert client.get("/api/overview", headers=H).json()["time_off_today"] is None
    with clean_db.begin() as c:
        make(c, start=date(2026, 10, 20), run=date(2026, 12, 17), upper=date(2027, 1, 2))
    assert client.get("/api/overview", headers=H).json()["time_off_today"] == \
        "no running until 17 Dec, no upper body until 2 Jan"


def test_time_off_today_when_away(client, clean_db, at):
    at(NOW)
    with clean_db.begin() as c:
        make(c, "vacation", None, start=date(2026, 10, 20), all=date(2026, 12, 27))
    assert client.get("/api/overview", headers=H).json()["time_off_today"] == "Vacation until 27 Dec"


def test_time_off_today_for_injury_with_all(client, clean_db, at):
    at(NOW)
    with clean_db.begin() as c:
        make(c, start=date(2026, 10, 20), all=date(2026, 10, 30))
    assert client.get("/api/overview", headers=H).json()["time_off_today"] == "Time off until 30 Oct"


def test_back_from_card_for_fourteen_days(client, clean_db, at):
    with clean_db.begin() as c:
        add_session(c, "run", NOW - timedelta(days=1), 1800)
        make(c, start=date(2026, 9, 1), run=date(2026, 10, 12))
    at(NOW)  # 14 days after the run restriction ended
    card = client.get("/api/overview", headers=H).json()["back_from"]
    assert card == {"title": "Back from: Knee operation", "label": "Knee operation"}
    at(NOW + timedelta(days=1))
    assert client.get("/api/overview", headers=H).json()["back_from"] is None


def test_back_from_card_without_a_label(client, clean_db, at):
    with clean_db.begin() as c:
        make(c, label=None, start=date(2026, 9, 1), swim=date(2026, 10, 20))
    at(NOW)
    assert client.get("/api/overview", headers=H).json()["back_from"] == \
        {"title": "Back from your operation", "label": None}


def test_a_vacation_never_makes_a_back_from_card(client, clean_db, at):
    with clean_db.begin() as c:
        make(c, "vacation", "Italy", start=date(2026, 10, 10), all=date(2026, 10, 24))
    at(NOW)
    assert client.get("/api/overview", headers=H).json()["back_from"] is None


def test_a_later_ending_vacation_does_not_hide_the_injury_card(client, clean_db, at):
    with clean_db.begin() as c:
        make(c, label="Knee operation", start=date(2026, 9, 1), swim=date(2026, 10, 20))
        make(c, "vacation", "Italy", start=date(2026, 10, 10), all=date(2026, 10, 24))
    at(NOW)
    assert client.get("/api/overview", headers=H).json()["back_from"]["label"] == "Knee operation"


def test_back_from_card_gone_when_off_again(client, clean_db, at):
    with clean_db.begin() as c:
        make(c, start=date(2026, 9, 1), run=date(2026, 10, 20))
        make(c, label=None, start=date(2026, 10, 25), run=date(2026, 11, 20))
    at(NOW)
    assert client.get("/api/overview", headers=H).json()["back_from"] is None


def test_back_from_picks_the_latest_ending(client, clean_db, at):
    with clean_db.begin() as c:
        make(c, label="Old knee", start=date(2026, 9, 1), run=date(2026, 10, 15))
        make(c, label="Shoulder", start=date(2026, 9, 1), upper=date(2026, 10, 22))
    at(NOW)
    assert client.get("/api/overview", headers=H).json()["back_from"]["label"] == "Shoulder"
