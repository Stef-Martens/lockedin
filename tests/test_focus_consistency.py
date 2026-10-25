from datetime import UTC, date, datetime, timedelta

from focus_helpers import add_gym, add_session

from lockedin.focus.consistency import comeback, totals, week_streak, weekly_volume

NOW = datetime(2026, 10, 26, 9, 0, tzinfo=UTC)  # Monday 10:00 in Brussels


def test_sunday_late_evening_is_last_week(conn):
    add_session(conn, "bike", datetime(2026, 10, 25, 22, 30, tzinfo=UTC), 3600, distance_m=30000)  # Sun 23:30 local
    add_session(conn, "bike", datetime(2026, 10, 26, 6, 0, tzinfo=UTC), 1800, distance_m=15000)    # Mon 07:00 local
    t = totals(conn, NOW)
    assert (t["week"]["bike"].sessions, t["week"]["bike"].time_s, t["week"]["bike"].distance_m) == (1, 1800, 15000)
    assert t["month"]["bike"].sessions == 2
    assert set(t["week"]) == {"bike", "run", "swim", "gym", "other"} and t["week"]["run"].sessions == 0


def test_duplicates_and_walks_are_not_counted(conn):
    ride = add_session(conn, "bike", NOW - timedelta(hours=2), 3600, source="zwift")
    add_session(conn, "bike", NOW - timedelta(hours=2), 3700, superseded_by=ride)
    add_session(conn, "other", NOW - timedelta(hours=1), 1200, sub_type="walking/generic")
    assert totals(conn, NOW)["week"]["bike"].sessions == 1 and totals(conn, NOW)["week"]["other"].sessions == 0
    week = weekly_volume(conn, NOW, 1)[0]
    assert (week["bike"], week["other"]) == (60, 0)


def test_weekly_volume_weeks(conn):
    add_gym(conn, datetime(2026, 10, 14, 17, 0, tzinfo=UTC), [("Bench Press (Barbell)", 80, 8, "normal")], duration_s=3000)
    rows = weekly_volume(conn, NOW, 3)
    assert [r["week_start"] for r in rows] == [date(2026, 10, 12), date(2026, 10, 19), date(2026, 10, 26)]
    assert rows[0]["gym"] == 50 and rows[1]["gym"] == 0


def two_a_week(conn, weeks_back):
    for w in weeks_back:
        monday = datetime(2026, 10, 26, 8, 0, tzinfo=UTC) - timedelta(weeks=w)
        add_session(conn, "run", monday + timedelta(days=1), 1800)
        add_session(conn, "run", monday + timedelta(days=3), 1800)


def test_week_streak(conn):
    two_a_week(conn, [1, 2, 3])
    assert week_streak(conn, NOW) == 3


def test_current_week_adds_once_it_has_two(conn):
    two_a_week(conn, [1, 2, 3])
    add_session(conn, "run", NOW - timedelta(hours=3), 1800)
    add_session(conn, "bike", NOW - timedelta(hours=1), 1800)
    assert week_streak(conn, NOW) == 4


def test_a_one_session_week_breaks_the_streak(conn):
    two_a_week(conn, [1, 3])
    add_session(conn, "run", datetime(2026, 10, 13, 8, 0, tzinfo=UTC), 1800)  # only one in week of 12 Oct
    assert week_streak(conn, NOW) == 1


def test_comeback_after_nine_days_suggests_their_main_sport(conn):
    for d in (9, 12, 15):
        add_session(conn, "bike", NOW - timedelta(days=d), 3600, source="zwift")
    add_session(conn, "run", NOW - timedelta(days=20), 1800)
    c = comeback(conn, NOW)
    assert c.days_since == 9 and c.last_session.sport == "bike"
    assert c.suggestion == "Ease back in: a 30-minute easy ride, just spinning."


def test_no_comeback_when_recent(conn):
    add_session(conn, "run", NOW - timedelta(days=3), 1800)
    assert comeback(conn, NOW) is None


def test_comeback_when_never_trained(conn):
    c = comeback(conn, NOW)
    assert c.days_since is None and c.last_session is None
    assert c.suggestion == "Ease back in: 30 minutes of something easy you enjoy."
