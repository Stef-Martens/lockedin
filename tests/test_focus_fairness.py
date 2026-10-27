"""Coverage for new starters, easy runs that are actually easy, and wins that compare like with like."""

from datetime import UTC, datetime, timedelta

from focus_helpers import add_gym, add_session
from sqlalchemy import text

from lockedin.focus.coverage import muscle_coverage
from lockedin.focus.mix import session_suggestions
from lockedin.focus.wins import recent_wins

NOW = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)
BENCH = "Bench Press (Barbell)"


def ago(days):
    return NOW - timedelta(days=days)


def chest(conn, cov):
    return next(c for c in cov if c.key == "mid_lower_chest")


def test_new_starter_is_averaged_over_the_weeks_they_have(conn):
    for d in (3, 10):
        add_gym(conn, ago(d), [(BENCH, 60, 10, "normal")] * 3)
    assert chest(conn, muscle_coverage(conn, NOW)).sets_per_week == 3.0  # 6 sets over 2 weeks, not 4


def test_a_break_still_counts_against_the_average(conn):
    add_gym(conn, ago(60), [(BENCH, 60, 10, "normal")] * 3)
    for d in (3, 10):
        add_gym(conn, ago(d), [(BENCH, 60, 10, "normal")] * 3)
    assert chest(conn, muscle_coverage(conn, NOW)).sets_per_week == 1.5


def test_easy_and_long_runs_sit_in_the_easy_band(conn):
    conn.execute(text("update profile set max_hr_override = 190"))
    for d in (2, 6, 11, 16):
        add_session(conn, "run", ago(d), 2700, avg_hr=148, distance_m=7000)
    long_run = next(s for s in session_suggestions(conn, NOW) if s.kind == "long")
    assert long_run.detail == "60–75 min easy (HR 124–148 bpm)"  # 65–78% of 190


def test_easy_run_without_zones(conn):
    for d in (2, 6, 11):
        add_session(conn, "run", ago(d), 2700, distance_m=7000)
    assert session_suggestions(conn, NOW)[0].detail == "60–75 min easy, at a pace you can talk at"


def test_fastest_run_compares_runs_of_about_the_same_distance(conn):
    add_session(conn, "run", ago(30), 3000, distance_m=10000, avg_pace=300.0)
    add_session(conn, "run", ago(2), 900, distance_m=3000, avg_pace=285.0)  # short and fast: not a 10k best
    assert [w for w in recent_wins(conn, NOW) if w.kind == "fastest_run"] == []

    add_session(conn, "run", ago(40), 1500, distance_m=5000, avg_pace=310.0)
    add_session(conn, "run", ago(1), 1450, distance_m=4800, avg_pace=302.0)
    fast = [w for w in recent_wins(conn, NOW) if w.kind == "fastest_run"]
    assert [(w.title, w.detail) for w in fast] == [("Fastest run", "5:02 /km over 4.8 km (was 5:10)")]


def test_fastest_swim_compares_like_distances(conn):
    add_session(conn, "swim", ago(30), 2400, distance_m=2000, swim_pace=120.0)
    add_session(conn, "swim", ago(2), 500, distance_m=400, swim_pace=110.0)
    assert [w for w in recent_wins(conn, NOW) if w.kind == "swim_pace"] == []


def test_one_busy_month_is_not_more_consistent_than_last_year(conn):
    for d in range(365 + 1, 365 + 56, 4):  # 14 sessions in those 8 weeks last year
        add_session(conn, "run", ago(d), 1800)
    for d in range(1, 28, 2):  # 14 in the last 4 weeks, nothing in the 4 before
        add_session(conn, "run", ago(d), 1800)
    assert not [w for w in recent_wins(conn, NOW) if w.kind == "consistency"]
    for d in (30, 35, 40):
        add_session(conn, "run", ago(d), 1800)
    wins = [w for w in recent_wins(conn, NOW) if w.kind == "consistency"]
    assert [w.detail for w in wins] == ["2.1 sessions a week over the last 8 weeks (was 1.8)"]
