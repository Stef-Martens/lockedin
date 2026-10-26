from datetime import UTC, date, datetime

from conftest import owner_headers
from focus_helpers import add_gym
from sqlalchemy import text

from lockedin.coach.prompt import turn_context
from lockedin.coach.tools import execute_tool
from lockedin.focus.musclemap import muscle_map
from lockedin.focus.suggest import gym_suggestions

NOW = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)
H = owner_headers()
BENCH = "Bench Press (Barbell)"


def set_prefs(conn, avoid=(), never=(), notes=""):
    conn.execute(text("update profile set avoid_muscles = :a, never_exercises = :n, coach_notes = :c"),
                 {"a": list(avoid), "n": list(never), "c": notes})


def test_preferences_round_trip(client):
    assert client.get("/api/preferences", headers=H).json() == {"avoid_muscles": [], "never_exercises": [], "coach_notes": ""}
    r = client.put("/api/preferences", headers=H, json={
        "avoid_muscles": ["lower_back"], "never_exercises": [" Good Morning (Barbell) ", "Good Morning (Barbell)"],
        "coach_notes": "Bad lower back"})
    assert r.status_code == 200
    assert client.get("/api/preferences", headers=H).json() == {
        "avoid_muscles": ["lower_back"], "never_exercises": ["Good Morning (Barbell)"], "coach_notes": "Bad lower back"}


def test_preferences_validation(client):
    assert client.put("/api/preferences", headers=H, json={"avoid_muscles": ["spleen"], "never_exercises": [],
                                                           "coach_notes": ""}).status_code == 422
    assert client.put("/api/preferences", headers=H, json={"avoid_muscles": [], "never_exercises": [],
                                                           "coach_notes": "x" * 1001}).status_code == 422
    assert client.get("/api/preferences").status_code == 401


def test_profile_put_keeps_preferences(client):
    client.put("/api/preferences", headers=H, json={"avoid_muscles": ["lower_back"], "never_exercises": [], "coach_notes": "n"})
    assert client.put("/api/profile", headers=H, json={"height_cm": 182}).status_code == 200
    assert client.get("/api/preferences", headers=H).json()["avoid_muscles"] == ["lower_back"]


def test_suggestions_skip_left_out_muscles(conn):
    add_gym(conn, datetime(2026, 10, 20, 18, tzinfo=UTC), [(BENCH, 60, 8, "normal")] * 3)
    assert "lower_back" in {s.muscle_key for s in gym_suggestions(conn, NOW, limit=20)}
    set_prefs(conn, avoid=["lower_back"])
    assert "lower_back" not in {s.muscle_key for s in gym_suggestions(conn, NOW, limit=20)}


def test_suggestions_skip_never_suggest_exercises(conn):
    add_gym(conn, datetime(2026, 10, 20, 18, tzinfo=UTC), [(BENCH, 60, 8, "normal")] * 3)
    rear = {s.muscle_key: s.exercise for s in gym_suggestions(conn, NOW, limit=20)}["rear_delt"]
    assert rear == "Rear Delt Reverse Fly (Machine)"
    set_prefs(conn, never=[rear])
    assert {s.muscle_key: s.exercise for s in gym_suggestions(conn, NOW, limit=20)}["rear_delt"] == "Face Pull"


def test_muscle_map_marks_left_out(conn):
    add_gym(conn, datetime(2026, 10, 20, 18, tzinfo=UTC), [("Back Extension (Hyperextension)", None, 12, "normal")] * 3)
    set_prefs(conn, avoid=["lower_back"])
    result = muscle_map(conn, NOW, date(2026, 10, 19))
    lower = next(m for m in result["muscles"] if m["key"] == "lower_back")
    assert lower["left_out"] is True and lower["sets"] > 0
    others = [m for m in result["muscles"] if m["key"] != "lower_back" and m["sets"] > 0]  # glutes/hamstrings as secondary
    assert result["total"] == 19 and result["trained_count"] == len(others)
    assert all(m["left_out"] is False for m in result["muscles"] if m["key"] != "lower_back")


def test_coach_context_lists_preferences(conn):
    set_prefs(conn, avoid=["lower_back"], never=["Good Morning (Barbell)"], notes="Bad lower back from an injury")
    ctx = turn_context(conn, NOW)
    assert "Lower back" in ctx and "Good Morning (Barbell)" in ctx and "Bad lower back from an injury" in ctx


def test_save_goal_links_an_exercise(clean_db):
    with clean_db.begin() as c:
        out, err = execute_tool("save_goal", {"action": "create", "text": "Bench 100 kg", "exercise": BENCH},
                                conn=c, engine=clean_db, now=NOW)
        assert not err
        assert c.execute(text("select exercise from goals")).scalar() == BENCH
