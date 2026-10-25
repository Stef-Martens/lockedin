from datetime import UTC, datetime, timedelta

from focus_helpers import add_gym, add_session

from lockedin.focus.coverage import muscle_coverage, unmapped_exercises
from lockedin.focus.suggest import gym_suggestions, suggested_load

NOW = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)
BENCH = "Bench Press (Barbell)"


def ago(days):
    return NOW - timedelta(days=days)


def by_key(items, key="key"):
    return {getattr(i, key): i for i in items}


def test_coverage_counts_primary_and_half_secondary(conn):
    for d in (3, 10, 17, 24):
        add_gym(conn, ago(d), [(BENCH, 40, 10, "warmup")] + [(BENCH, 80, 8, "normal")] * 3)
    cov = by_key(muscle_coverage(conn, NOW))
    assert cov["mid_lower_chest"].sets_per_week == 3.0
    assert cov["upper_chest"].sets_per_week == 1.5 and cov["triceps"].sets_per_week == 1.5
    assert cov["mid_lower_chest"].status == "low"  # target 6–12
    assert cov["calves"].sets_per_week == 0 and cov["calves"].status == "low"
    assert cov["forearms"].status == "ok"  # target_low 0 is never low


def test_coverage_high_status(conn):
    for d in (3, 10, 17, 24):
        add_gym(conn, ago(d), [("Lateral Raise (Dumbbell)", 10, 12, "normal")] * 30)
    assert by_key(muscle_coverage(conn, NOW))["side_delt"].status == "high"  # 30/week > 16 × 1.5


def test_no_gym_means_no_coverage(conn):
    add_session(conn, "run", ago(2), 1800)
    assert muscle_coverage(conn, NOW) == []


def test_unmapped_exercises(conn):
    add_gym(conn, ago(5), [("Zercher Squat", 60, 8, "normal"), (BENCH, 80, 8, "normal")])
    assert unmapped_exercises(conn, NOW) == ["Zercher Squat"]


def test_suggested_load_rounding():
    assert suggested_load(100) == 70.0   # 71.4 → 70.0 (2.5 steps)
    assert suggested_load(26) == 18.0    # 18.6 → 18 (1 kg steps below 20)


def test_new_exercise_estimated_from_related_lift(conn):
    add_gym(conn, ago(4), [("Leg Press Horizontal (Machine)", 150, 10, "normal")])  # e1RM 200
    calves = by_key(gym_suggestions(conn, NOW, limit=20), "muscle_key")["calves"]
    assert calves.exercise == "Standing Calf Raise (Machine)"
    assert calves.weight_kg == 55.0 and calves.estimate is True and calves.per_dumbbell is False
    assert calves.reason == "Calves: 0 sets/week, aim for 6–12"


def test_known_exercise_uses_own_history(conn):
    add_gym(conn, ago(42), [("Triceps Extension (Cable)", 30, 10, "normal")])  # e1RM 40, not in the last 4 weeks
    add_gym(conn, ago(3), [("Leg Extension (Machine)", 50, 12, "normal")])
    tri = by_key(gym_suggestions(conn, NOW, limit=20), "muscle_key")["triceps"]
    assert (tri.exercise, tri.estimate, tri.weight_kg) == ("Triceps Extension (Cable)", False, 27.5)


def test_dumbbell_weights_are_per_dumbbell(conn):
    add_gym(conn, ago(3), [("Overhead Press (Dumbbell)", 20, 10, "normal")] * 3)
    front = by_key(gym_suggestions(conn, NOW, limit=20), "muscle_key")["front_delt"]
    assert front.exercise == "Overhead Press (Dumbbell)" and front.per_dumbbell is True


def test_bodyweight_suggestion_has_reps_not_weight(conn):
    add_gym(conn, ago(3), [("Pull Up", None, 10, "normal")])
    lats = by_key(gym_suggestions(conn, NOW, limit=20), "muscle_key")["lats"]
    assert (lats.exercise, lats.weight_kg, lats.reps) == ("Pull Up", None, "8–10")


def test_most_neglected_muscle_first(conn):
    for d in (3, 10, 17, 24):
        add_gym(conn, ago(d), [(BENCH, 80, 8, "normal")] * 3)
    keys = [s.muscle_key for s in gym_suggestions(conn, NOW, limit=20)]
    assert keys.index("calves") < keys.index("mid_lower_chest")
    assert len(gym_suggestions(conn, NOW)) == 3


def test_empty_db_has_no_suggestions(conn):
    assert gym_suggestions(conn, NOW) == []
