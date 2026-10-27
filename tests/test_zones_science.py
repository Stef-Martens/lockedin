from datetime import UTC, datetime, timedelta

import pytest
from focus_helpers import add_session
from sqlalchemy import text

from lockedin.fit.metrics import rolling_means
from lockedin.focus.effort import classify_effort
from lockedin.focus.sessions import Session
from lockedin.focus.zones import hr_zone, hr_zone_bounds, max_hr_at, power_zone_bounds

NOW = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)


def S(sport="run", duration_s=3600, **kw) -> Session:
    base = dict(id=1, sport=sport, sub_type=None, source="healthfit", start_at=NOW, duration_s=duration_s,
                distance_m=None, avg_hr=None, max_hr=None, np=None, avg_power=None, best_20m_power=None,
                avg_pace_s_per_km=None, swim_pace_s_per_100m=None)
    return Session(**(base | kw))


def classify(s, **kw):
    args = dict(power=None, hr=None, ftp=None, max_hr=None, median_duration_s=None, median_swim_pace=None) | kw
    return classify_effort(s, **args)


def test_hard_starts_at_87_percent_of_max():
    assert hr_zone(165, 190) == 3 and hr_zone(166, 190) == 4  # 86.8 % vs 87.4 %
    assert hr_zone(156, 190) == 3 and hr_zone(155, 190) == 2      # 82 % starts zone 3
    assert hr_zone_bounds(200) == {1: (0, 144), 2: (144, 164), 3: (164, 174), 4: (174, 184), 5: (184, 200)}


def test_a_steady_aerobic_run_is_not_hard():
    assert classify(S(), hr=[160] * 3600, max_hr=190) == "steady"  # 84 %
    assert classify(S(), hr=[150] * 3600, max_hr=190) == "easy"    # 79 %, the old "hard"
    assert classify(S(), hr=[150] * 2700 + [170] * 900, max_hr=190) == "hard"  # 15 min ≥ 87 %


def test_average_fallbacks_use_the_zone_boundaries():
    assert classify(S(avg_hr=150), max_hr=190) == "easy"
    assert classify(S(avg_hr=160), max_hr=190) == "steady"
    assert classify(S(avg_hr=166), max_hr=190) == "hard"
    assert classify(S("bike", np=185), ftp=250) == "easy"     # IF 0.74
    assert classify(S("bike", np=220), ftp=250) == "steady"   # IF 0.88
    assert classify(S("bike", np=230), ftp=250) == "hard"     # IF 0.92


def test_zwift_surges_dont_make_a_ride_hard():
    surgy = ([190] * 25 + [330] * 5) * 120  # 5 s kicks every 30 s: raw, 17 % of samples are zone 5
    assert classify(S("bike"), power=surgy, ftp=250) == "steady"


def test_rolling_means_skip_windows_across_a_gap():
    t = list(range(40)) + list(range(100, 140))
    assert len(rolling_means([150] * 80, t, 30, max_gap_s=10, gap=None)) == 22  # 11 full windows each side
    assert rolling_means([100] * 30 + [200] * 30, list(range(60)), 30)[-1] == pytest.approx(200)


def test_power_zone_5_is_open_ended():
    assert power_zone_bounds(250)[5] == (265, None) and power_zone_bounds(250)[4] == (228, 262)


def test_max_hr_from_best_30_seconds_not_a_spike(conn):
    add_session(conn, "run", NOW - timedelta(days=20), 600, max_hr=212, hr=[150] * 300 + [180] * 60 + [212] + [150] * 239)
    add_session(conn, "run", NOW - timedelta(days=40), 600, max_hr=176, hr=[176] * 600)
    assert max_hr_at(conn, NOW) == 181  # 30 s around 180, the single 212 barely moves it


def test_max_hr_ignores_impossible_samples(conn):
    add_session(conn, "run", NOW - timedelta(days=20), 600, max_hr=250, hr=[178] * 100 + [250] * 40 + [178] * 460)
    assert max_hr_at(conn, NOW) == 178


def test_max_hr_without_streams_takes_the_second_highest(conn):
    for m in (205, 188, 180):
        add_session(conn, "run", NOW - timedelta(days=m - 170), 1800, max_hr=m)
    assert max_hr_at(conn, NOW) == 188


def test_max_hr_from_age_uses_tanaka(conn):
    conn.execute(text("update profile set date_of_birth = '1986-01-01'"))
    assert max_hr_at(conn, NOW) == 180  # 208 − 0.7 × 40


def test_override_still_wins(conn):
    add_session(conn, "run", NOW - timedelta(days=20), 600, max_hr=190, hr=[190] * 600)
    conn.execute(text("update profile set max_hr_override = 185"))
    assert max_hr_at(conn, NOW) == 185
