from datetime import UTC, date, datetime, timedelta

import pytest
from focus_helpers import add_gym, add_session
from sqlalchemy import text

from lockedin.focus.trends import bike_trends, gym_exercise_progress, gym_weekly_volume, run_trends, swim_trends

NOW = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)  # a Monday: "N days ago" sessions sit in the week of 19 Oct
LAST_WEEK = date(2026, 10, 19)


def week(rows, ws=LAST_WEEK):
    return next(r for r in rows if r["week_start"] == ws)


def test_run_aerobic_efficiency(conn):
    add_session(conn, "run", NOW - timedelta(days=3), 2400, avg_pace=300.0, avg_hr=150, distance_m=8000)
    r = run_trends(conn, NOW)
    assert r["runs"][0]["aerobic_efficiency"] == pytest.approx(1.333, abs=0.001)  # 200 m/min ÷ 150 bpm
    assert week(r["weekly"])["km"] == 8.0 and len(r["weekly"]) == 26


def test_bike_efficiency_and_ftp(conn):
    add_session(conn, "bike", NOW - timedelta(days=3), 3600, source="zwift", np=220, avg_hr=150, best_20m_power=240)
    b = bike_trends(conn, NOW)
    assert b["rides"][0]["efficiency"] == pytest.approx(1.467, abs=0.001)
    assert b["ftp"] == pytest.approx(228)  # 0.95 × 240
    assert set(b["mix"].counts) == {"easy", "steady", "hard", "long"}


def test_swim_weekly_metres(conn):
    add_session(conn, "swim", NOW - timedelta(days=1), 1800, distance_m=1000, swim_pace=180.0)
    s = swim_trends(conn, NOW)
    assert week(s["weekly"])["m"] == 1000 and s["swims"][0]["pace_s_per_100m"] == 180.0


def test_gym_weekly_volume_excludes_warmups(conn):
    add_gym(conn, NOW - timedelta(days=1), [("Bench Press (Barbell)", 40, 10, "warmup"), ("Bench Press (Barbell)", 80, 8, "normal"),
                                            ("Pull Up", None, 10, "normal")])
    assert week(gym_weekly_volume(conn, NOW, 2))["volume_kg"] == 640


def test_exercise_progress_best_set_per_session(conn):
    add_gym(conn, NOW - timedelta(days=8), [("Bench Press (Barbell)", 75, 7, "normal"), ("Bench Press (Barbell)", 70, 8, "normal")])
    add_gym(conn, NOW - timedelta(days=1), [("Bench Press (Barbell)", 80, 6, "normal")])
    ex = conn.execute(text("select id from exercises where name = 'Bench Press (Barbell)'")).scalar()
    p = gym_exercise_progress(conn, ex)
    assert p["exercise"] == "Bench Press (Barbell)"
    assert [(s["best_e1rm"], s["best_set"]["weight_kg"], s["best_set"]["reps"]) for s in p["sessions"]] == [(92.5, 75, 7), (96.0, 80, 6)]
    assert p["sessions"][0]["date"] == date(2026, 10, 18)
