from datetime import UTC, date, datetime

import pytest
from conftest import owner_headers
from focus_helpers import add_gym, add_session

from lockedin.focus.coverage import muscle_coverage
from lockedin.focus.musclemap import muscle_map

NOW = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)  # a Monday
WEEK = date(2026, 10, 19)
BENCH = "Bench Press (Barbell)"
LEGS = "Leg Press Horizontal (Machine)"


def at(day: int, hour: int = 18, month: int = 10) -> datetime:
    return datetime(2026, month, day, hour, 0, tzinfo=UTC)


def by_key(result: dict) -> dict:
    return {m["key"]: m for m in result["muscles"]}


def test_counts_one_week_of_sets(conn):
    add_gym(conn, at(20), [(BENCH, 40, 10, "warmup")] + [(BENCH, 60, 8, "normal")] * 3)
    result = muscle_map(conn, NOW, WEEK)
    m = by_key(result)
    assert result["week_start"] == "2026-10-19" and result["is_current"] is False
    assert m["mid_lower_chest"]["sets"] == 3 and m["triceps"]["sets"] == 1.5
    assert m["mid_lower_chest"]["days"] == [{"date": "2026-10-20", "exercises": [{"name": BENCH, "sets": 3.0}]}]
    assert result["trained_count"] == 4
    assert len(result["muscles"]) == 20


def test_week_boundary_across_dst(conn):
    # 25 Oct 2026: clocks went back that morning, so Brussels is UTC+1 by the evening.
    add_gym(conn, datetime(2026, 10, 25, 22, 30, tzinfo=UTC), [(BENCH, 60, 8, "normal")], title="Sunday late")
    add_gym(conn, datetime(2026, 10, 25, 23, 30, tzinfo=UTC), [(BENCH, 60, 8, "normal")] * 2, title="Monday early")
    assert by_key(muscle_map(conn, NOW, WEEK))["mid_lower_chest"]["sets"] == 1
    assert by_key(muscle_map(conn, NOW, date(2026, 10, 26)))["mid_lower_chest"]["sets"] == 2


def test_coverage_unchanged(conn):
    add_gym(conn, at(20), [(BENCH, 60, 8, "normal")] * 4)
    cov = {c.key: c for c in muscle_coverage(conn, NOW)}
    assert cov["mid_lower_chest"].sets_per_week == 1.0 and cov["triceps"].sets_per_week == 0.5
    assert cov["mid_lower_chest"].status == "low"


def test_cardio_is_a_separate_layer(conn):
    add_session(conn, "bike", at(25, 9), 46 * 60, source="zwift")
    add_session(conn, "run", at(23), 30 * 60, sub_type="walking")
    original = add_session(conn, "bike", at(22), 60 * 60, source="zwift")
    add_session(conn, "bike", at(22), 60 * 60, superseded_by=original)
    result = muscle_map(conn, NOW, WEEK)
    assert result["cardio"] == [{"sport": "bike", "minutes": 106, "days": ["2026-10-22", "2026-10-25"]}]
    quads = by_key(result)["quads"]
    assert quads["cardio"] == [{"sport": "bike", "minutes": 106}] and quads["sets"] == 0
    assert by_key(result)["lats"]["cardio"] == []
    assert result["trained_count"] == 0


def test_swim_hits_the_upper_body(conn):
    add_session(conn, "swim", at(21), 40 * 60)
    m = by_key(muscle_map(conn, NOW, WEEK))
    assert m["lats"]["cardio"] == [{"sport": "swim", "minutes": 40}] and m["quads"]["cardio"] == []


def test_last_trained_is_before_the_selected_week(conn):
    add_gym(conn, at(9), [(LEGS, 100, 10, "normal")])
    assert by_key(muscle_map(conn, NOW, WEEK))["quads"]["last_trained"] == "2026-10-09"
    assert by_key(muscle_map(conn, NOW, date(2026, 10, 5)))["quads"]["last_trained"] is None


def test_history_six_weeks_ending_with_selected(conn):
    add_gym(conn, at(13), [(BENCH, 60, 8, "normal")] * 2)
    add_gym(conn, at(20), [(BENCH, 60, 8, "normal")] * 3)
    history = by_key(muscle_map(conn, NOW, WEEK))["mid_lower_chest"]["history"]
    assert [h["week_start"] for h in history] == ["2026-09-14", "2026-09-21", "2026-09-28", "2026-10-05", "2026-10-12", "2026-10-19"]
    assert [h["sets"] for h in history] == [0, 0, 0, 0, 2, 3]


def test_main_lift_trend_new_and_not_lately(conn):
    add_gym(conn, at(21, month=9), [(BENCH, 60, 8, "normal")])   # e1RM 76.0
    add_gym(conn, at(20), [(BENCH, 80, 8, "normal")])            # e1RM 101.3
    lift = by_key(muscle_map(conn, NOW, WEEK))["mid_lower_chest"]["lift"]
    assert lift["exercise"] == BENCH and lift["status"] == "trend"
    assert lift["first_e1rm"] == pytest.approx(76.0, abs=0.1) and lift["latest_e1rm"] == pytest.approx(101.3, abs=0.1)

    single = by_key(muscle_map(conn, NOW, date(2026, 9, 21)))["mid_lower_chest"]["lift"]
    assert single["status"] == "new" and single["latest_e1rm"] == pytest.approx(76.0, abs=0.1)

    assert by_key(muscle_map(conn, NOW, None))["mid_lower_chest"]["lift"]["status"] == "trend"  # last bench 6 days ago
    # A month later only the 20 Oct session is in the 8-week window, and it's over 28 days old.
    later = by_key(muscle_map(conn, datetime(2026, 11, 25, 12, tzinfo=UTC), date(2026, 11, 23)))
    assert later["mid_lower_chest"]["lift"]["status"] == "not_lately"


def test_suggestions_only_on_current_week(conn):
    add_gym(conn, at(20), [(BENCH, 60, 8, "normal")] * 3)
    current = muscle_map(conn, NOW, None)
    assert current["is_current"] is True
    assert any(m["suggestion"] for m in current["muscles"])
    assert not any(m["suggestion"] for m in muscle_map(conn, NOW, WEEK)["muscles"])


def test_empty_database(conn):
    result = muscle_map(conn, NOW, None)
    assert len(result["muscles"]) == 20 and all(m["sets"] == 0 for m in result["muscles"])
    assert result["first_week"] is None and result["trained_count"] == 0 and result["cardio"] == []
    assert all(m["lift"] is None and m["last_trained"] is None for m in result["muscles"])


def test_first_week(conn):
    add_session(conn, "bike", at(15, month=9), 3600, source="zwift")
    add_gym(conn, at(20), [(BENCH, 60, 8, "normal")])
    assert muscle_map(conn, NOW, None)["first_week"] == "2026-09-14"


def test_future_week_clamps_to_current(conn):
    result = muscle_map(conn, NOW, date(2027, 1, 4))
    assert result["week_start"] == "2026-10-26" and result["is_current"] is True


def test_unmapped_exercise_is_ignored(conn):
    add_gym(conn, at(20), [("Mystery Machine", 50, 10, "normal")] * 3)
    result = muscle_map(conn, NOW, WEEK)
    assert result["trained_count"] == 0 and all(m["lift"] is None for m in result["muscles"])


def test_route(client):
    r = client.get("/api/muscle-map?week=2026-10-21", headers=owner_headers())
    assert r.status_code == 200 and r.json()["week_start"] == "2026-10-19"
    assert client.get("/api/muscle-map?week=nope", headers=owner_headers()).status_code == 422
    assert client.get("/api/muscle-map").status_code == 401
