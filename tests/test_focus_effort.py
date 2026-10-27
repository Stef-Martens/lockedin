from datetime import UTC, datetime, timedelta

from focus_helpers import add_session
from sqlalchemy import text

from lockedin.focus.effort import classify_effort
from lockedin.focus.sessions import Session, counted_sessions
from lockedin.focus.zones import hr_zone, hr_zone_bounds, max_hr_at, power_zone

NOW = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)


def S(sport="bike", duration_s=3600, **kw) -> Session:
    base = dict(id=1, sport=sport, sub_type=None, source="zwift", start_at=NOW, duration_s=duration_s, distance_m=None,
                avg_hr=None, max_hr=None, np=None, avg_power=None, best_20m_power=None, avg_pace_s_per_km=None,
                swim_pace_s_per_100m=None)
    return Session(**(base | kw))


def classify(s, **kw):
    args = dict(power=None, hr=None, ftp=None, max_hr=None, median_duration_s=None, median_swim_pace=None) | kw
    return classify_effort(s, **args)


def test_hr_zones():
    assert hr_zone(140, 190) == 2 and hr_zone(175, 190) == 5
    assert hr_zone(164, 200) == 3  # exactly 82 % is the start of zone 3
    assert hr_zone_bounds(190)[2] == (137, 156)


def test_power_zones():
    assert power_zone(200, 250) == 3 and power_zone(270, 250) == 5 and power_zone(139, 250) == 1


def test_max_hr_override_wins(conn):
    conn.execute(text("update profile set max_hr_override = 195"))
    assert max_hr_at(conn, NOW) == 195


def test_max_hr_from_observed(conn):
    add_session(conn, "run", NOW - timedelta(days=30), 1800, max_hr=188)
    assert max_hr_at(conn, NOW) == 188


def test_implausible_observed_falls_back_to_age(conn):
    add_session(conn, "run", NOW - timedelta(days=30), 1800, max_hr=250)
    conn.execute(text("update profile set date_of_birth = '1995-04-12'"))
    assert max_hr_at(conn, NOW) == 186  # Tanaka: 208 − 0.7 × 31


def test_no_max_hr_at_all(conn):
    assert max_hr_at(conn, NOW) is None


def test_easy_ride_by_power():
    assert classify(S(), power=[140] * 3600, ftp=250) == "easy"


def test_interval_ride_is_hard():
    p = ([280] * 240 + [150] * 240) * 7 + [150] * 240
    assert classify(S(), power=p, ftp=250) == "hard"


def test_steady_ride():
    assert classify(S(), power=[210] * 3600, ftp=250) == "steady"


def test_long_easy_run_by_hr():
    s = S("run", duration_s=5400, source="healthfit")
    assert classify(s, hr=[129] * 5400, max_hr=190, median_duration_s=2700) == "long"  # 68 % of max


def test_hard_run_from_average_only():
    assert classify(S("run", avg_hr=167), max_hr=190) == "hard"  # 88 %


def test_swim_by_pace_vs_median():
    assert classify(S("swim", swim_pace_s_per_100m=113.0), median_swim_pace=120.0) == "hard"
    assert classify(S("swim", swim_pace_s_per_100m=130.0), median_swim_pace=120.0) == "easy"


def test_no_data_is_unclassified():
    assert classify(S("run")) is None


def test_counted_sessions_skip_walks_and_duplicates(conn):
    ride = add_session(conn, "bike", NOW - timedelta(days=1), 3600, source="zwift")
    add_session(conn, "bike", NOW - timedelta(days=1), 3700, superseded_by=ride)
    add_session(conn, "other", NOW - timedelta(days=2), 1200, sub_type="walking/generic")
    got = counted_sessions(conn, NOW - timedelta(days=7), NOW)
    assert [s.id for s in got] == [ride]
