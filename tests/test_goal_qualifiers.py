"""Goals with a rep count or a time: the bar measures that, or there is no bar."""

from datetime import UTC, datetime

import pytest
from focus_helpers import add_gym, add_session
from test_goal_progress import BENCH, NOW, goal

from lockedin.goals.progress import progress

DAY = datetime(2026, 10, 20, 17, tzinfo=UTC)


@pytest.mark.parametrize("words", ["Bench 80 kg for 5 reps", "Bench 80 kg x5", "Bench 80kg × 5", "5 reps at 80 kg",
                                   "Bench 5x80 kg"])
def test_rep_goal_uses_real_sets_not_e1rm(conn, words):
    add_gym(conn, DAY, [(BENCH, 60, 5, "warmup"), (BENCH, 65, 7, "normal"), (BENCH, 75, 3, "normal")])  # 65×7: Epley 80.2
    p = progress(conn, NOW, goal(conn, words, "gym", exercise=BENCH))
    assert p["label"] == "65 / 80 kg × 5" and p["fraction"] == pytest.approx(65 / 80)


def test_rep_goal_done_with_a_set_at_or_above_the_reps(conn):
    add_gym(conn, DAY, [(BENCH, 80, 6, "normal"), (BENCH, 85, 2, "normal")])
    p = progress(conn, NOW, goal(conn, "Bench 80 kg for 5 reps", "gym", exercise=BENCH))
    assert p["label"] == "80 / 80 kg × 5" and p["fraction"] == 1


def test_high_rep_sets_count_without_an_e1rm(conn):
    add_gym(conn, DAY, [(BENCH, 50, 15, "normal")])
    conn.exec_driver_sql("update gym_sets set e1rm = null")
    assert progress(conn, NOW, goal(conn, "Bench 60 kg for 10 reps", "gym", exercise=BENCH))["label"] == "50 / 60 kg × 10"


def test_rep_goal_with_no_set_that_long_has_no_bar(conn):
    add_gym(conn, DAY, [(BENCH, 90, 3, "normal")])
    assert progress(conn, NOW, goal(conn, "Bench 80 kg for 5 reps", "gym", exercise=BENCH)) is None


def test_plain_and_single_rep_goals_stay_on_e1rm(conn):
    add_gym(conn, DAY, [(BENCH, 72, 10, "normal")])  # e1RM 96
    for words in ("Bench 100 kg", "Bench 100 kg 1RM", "Bench 100 kg for 1 rep"):
        assert progress(conn, NOW, goal(conn, words, "gym", exercise=BENCH))["label"] == "96 / 100 kg est. 1RM"


def run(conn, km: float, seconds: int, sport="run", day=DAY):
    add_session(conn, sport, day, seconds, distance_m=km * 1000)


@pytest.mark.parametrize("words", ["Run 5k under 25 min", "Run 5 km in 25:00", "Sub 25 5k", "5k in 25 minutes"])
def test_run_time_goal_shows_best_time(conn, words):
    run(conn, 5.02, 27 * 60)
    run(conn, 8, 40 * 60)  # longer: no 5 km time in it to read
    p = progress(conn, NOW, goal(conn, words, "run"))
    assert p["label"] == "27:00 / 25:00 for 5 km" and p["fraction"] == pytest.approx(25 / 27)


def test_any_run_of_the_distance_within_the_time_completes_it(conn):
    run(conn, 5.4, 24 * 60 + 50)
    p = progress(conn, NOW, goal(conn, "Run 5k under 25 min", "run"))
    assert p["fraction"] == 1 and p["label"] == "24:50 / 25:00 for 5 km"


def test_run_time_goal_unmeasurable_without_a_run_that_long(conn):
    run(conn, 4.8, 22 * 60)   # short: pace says done, but the goal isn't
    run(conn, 10, 55 * 60)    # long and slow: no reliable 5 km time
    assert progress(conn, NOW, goal(conn, "Run 5k under 25 min", "run")) is None


def test_half_marathon_in_hours(conn):
    run(conn, 21.2, 6600)
    for words in ("Run a half marathon in 1:45", "Half marathon under 1:45 h", "Half marathon sub 1h45"):
        assert progress(conn, NOW, goal(conn, words, "run"))["label"] == "1:50:00 / 1:45:00 for 21.1 km"


def test_swim_time_goal(conn):
    run(conn, 1.5, 32 * 60, sport="swim")
    p = progress(conn, NOW, goal(conn, "Swim 1500 m in 30 min", "swim"))
    assert p["label"] == "32:00 / 30:00 for 1.5 km"


def test_distance_goal_without_a_time_still_uses_the_longest(conn):
    run(conn, 8.2, 2800)
    assert progress(conn, NOW, goal(conn, "Run a 10K in March", "run"))["label"] == "8.2 / 10 km"
    assert progress(conn, NOW, goal(conn, "Run a marathon", "run"))["label"] == "8.2 / 42.2 km"


@pytest.mark.parametrize("words, area", [
    ("Run 10k at 5:00/km pace", "run"), ("Run 5k under 2 min", "run"), ("Ride 100 km under 4 h", "bike"),
    ("Hold 250 W for 20 min", "bike"),
])
def test_ambiguous_time_and_pace_goals_get_no_bar(conn, words, area):
    conn.exec_driver_sql("update profile set ftp_override = 240")
    run(conn, 10, 50 * 60)
    run(conn, 100, 4 * 3600, sport="bike")
    assert progress(conn, NOW, goal(conn, words, area)) is None
