from datetime import UTC, datetime, timedelta

from focus_helpers import add_gym, add_session

from lockedin.focus.wins import plateaus, recent_wins

NOW = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)
BENCH = "Bench Press (Barbell)"


def test_e1rm_pr(conn):
    add_gym(conn, NOW - timedelta(days=30), [(BENCH, 75, 7, "normal")])  # 92.5
    add_gym(conn, NOW - timedelta(days=2), [(BENCH, 80, 6, "normal")])   # 96.0
    wins = [w for w in recent_wins(conn, NOW) if w.kind == "e1rm_pr"]
    assert [(w.title, w.detail) for w in wins] == [("New best: Bench Press (Barbell)", "est. 1RM 96.0 kg (was 92.5)")]


def test_first_ever_session_is_not_a_win(conn):
    add_gym(conn, NOW - timedelta(days=2), [(BENCH, 80, 6, "normal")])
    add_session(conn, "run", NOW - timedelta(days=1), 2400, distance_m=8000, avg_pace=300.0)
    assert recent_wins(conn, NOW) == []


def test_power_and_distance_prs(conn):
    add_session(conn, "bike", NOW - timedelta(days=40), 3600, source="zwift", best_20m_power=241, distance_m=30000)
    add_session(conn, "bike", NOW - timedelta(days=3), 5400, source="zwift", best_20m_power=248, distance_m=45000)
    kinds = {w.kind: w.detail for w in recent_wins(conn, NOW)}
    assert kinds["power_pr"] == "248 W (was 241)"
    assert kinds["longest"] == "45.0 km ride (was 30.0)"


def test_fastest_run_only_counts_runs_of_3km(conn):
    add_session(conn, "run", NOW - timedelta(days=30), 1650, distance_m=5000, avg_pace=330.0)
    add_session(conn, "run", NOW - timedelta(days=20), 500, distance_m=2000, avg_pace=250.0)  # too short to count
    add_session(conn, "run", NOW - timedelta(days=2), 560, distance_m=2000, avg_pace=280.0)   # too short
    add_session(conn, "run", NOW - timedelta(days=1), 1550, distance_m=5000, avg_pace=310.0)
    fast = [w for w in recent_wins(conn, NOW) if w.kind == "fastest_run"]
    assert [w.detail for w in fast] == ["5:10 /km over 5.0 km (was 5:30)"]


def test_watch_duplicate_is_never_a_win(conn):
    ride = add_session(conn, "bike", NOW - timedelta(days=40), 3600, source="zwift", distance_m=30000)
    add_session(conn, "bike", NOW - timedelta(days=3), 3600, source="zwift", distance_m=20000)
    add_session(conn, "bike", NOW - timedelta(days=3), 3600, distance_m=90000, superseded_by=ride)
    assert [w for w in recent_wins(conn, NOW) if w.kind == "longest"] == []


def test_consistency_vs_last_year(conn):
    add_session(conn, "run", NOW - timedelta(days=365 + 5), 1800)
    for d in (2, 5, 9):
        add_session(conn, "run", NOW - timedelta(days=d), 1800)
    assert any(w.kind == "consistency" for w in recent_wins(conn, NOW))


def test_gym_plateau(conn):
    for d in (80, 70):
        add_gym(conn, NOW - timedelta(days=d), [(BENCH, 75, 7, "normal")])
    for d in (35, 25, 15, 5):
        add_gym(conn, NOW - timedelta(days=d), [(BENCH, 75, 6, "normal")])
    p = plateaus(conn, NOW)
    assert [x.title for x in p] == ["Bench Press (Barbell) has stalled"]
    assert p[0].suggestion.startswith("Change the stimulus")


def test_no_plateau_when_improving(conn):
    for d in (80, 70):
        add_gym(conn, NOW - timedelta(days=d), [(BENCH, 70, 6, "normal")])
    for d in (35, 25, 15, 5):
        add_gym(conn, NOW - timedelta(days=d), [(BENCH, 80, 6, "normal")])
    assert plateaus(conn, NOW) == []


def test_no_plateau_with_too_few_sessions(conn):
    add_gym(conn, NOW - timedelta(days=70), [(BENCH, 75, 7, "normal")])
    for d in (25, 5):
        add_gym(conn, NOW - timedelta(days=d), [(BENCH, 75, 6, "normal")])
    assert plateaus(conn, NOW) == []


def test_bike_plateau(conn):
    for d in (100, 80):
        add_session(conn, "bike", NOW - timedelta(days=d), 3600, source="zwift", best_20m_power=250)
    for d in (50, 40, 20, 5):
        add_session(conn, "bike", NOW - timedelta(days=d), 3600, source="zwift", best_20m_power=240)
    assert [x.kind for x in plateaus(conn, NOW)] == ["bike_power"]


def test_previous_best_is_shown_with_one_decimal(conn):
    add_gym(conn, NOW - timedelta(days=30), [("Lateral Raise (Dumbbell)", 28, 11, "normal")])  # 38.2666…
    add_gym(conn, NOW - timedelta(days=2), [("Lateral Raise (Dumbbell)", 32, 10, "normal")])   # 42.666…
    (w,) = [w for w in recent_wins(conn, NOW) if w.kind == "e1rm_pr"]
    assert w.detail == "est. 1RM 42.7 kg (was 38.3)"


def test_high_rep_set_is_never_a_best(conn):
    add_gym(conn, NOW - timedelta(days=30), [(BENCH, 75, 7, "normal")])   # 92.5
    add_gym(conn, NOW - timedelta(days=2), [(BENCH, 70, 15, "normal")])   # Epley 105, but 15 reps
    assert [w for w in recent_wins(conn, NOW) if w.kind == "e1rm_pr"] == []
