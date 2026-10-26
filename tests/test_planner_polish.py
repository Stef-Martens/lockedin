from datetime import UTC, datetime, timedelta

import pytest
from conftest import owner_headers
from focus_helpers import add_gym
from sqlalchemy import text

from lockedin.app import app
from lockedin.coach.tools import execute_tool
from lockedin.goals.steer import goal_muscles
from lockedin.plan.goals import goal_for
from lockedin.routes.overview import get_now

NOW = datetime(2026, 10, 26, 8, 0, tzinfo=UTC)
H = owner_headers()
CHEST = "Chest - Schouders - Triceps"
BENCH, INCLINE, OHP = "Bench Press (Barbell)", "Incline Bench Press (Dumbbell)", "Overhead Press (Dumbbell)"
KNOWN = ["Bench Press (Barbell)", "Incline Bench Press (Dumbbell)", "Squat (Barbell)", "Bulgarian Split Squat",
         "Deadlift (Barbell)", "Romanian Deadlift (Barbell)"]


@pytest.mark.parametrize("words, exercise", [
    ("Incline bench press 40 kg dumbbells", BENCH),
    ("Bulgarian split squat with 20 kg", "Squat (Barbell)"),
    ("Romanian deadlift 100", "Deadlift (Barbell)"),
])
def test_goal_words_for_a_longer_exercise_dont_tie_to_the_shorter_one(words, exercise):
    assert goal_for(exercise, [{"text": words, "exercise": None, "status": "active"}], known=KNOWN) is None


def test_goal_words_still_tie_to_the_right_lift():
    g = {"text": "Incline bench press 40 kg dumbbells", "exercise": None, "status": "active"}
    assert goal_for(INCLINE, [g], known=KNOWN) == g
    bench = {"text": "Bench 100 kg", "exercise": None, "status": "active"}
    assert goal_for(BENCH, [bench], known=KNOWN) == bench


@pytest.fixture
def clock():
    state = {"now": NOW}
    app.dependency_overrides[get_now] = lambda: state["now"]
    return state


def chest_day(engine, when):
    with engine.begin() as c:
        add_gym(c, when, [(BENCH, 60, 12, "normal")] * 3 + [(INCLINE, 50, 10, "normal")] * 3 + [(OHP, 40, 10, "normal")] * 3,
                title=CHEST)


def plan(client):
    return client.get("/api/plan", params={"day": CHEST}, headers=H).json()


def test_plan_rebuilds_when_a_break_starts_during_the_day(client, clean_db, clock):
    chest_day(clean_db, NOW - timedelta(days=7) + timedelta(hours=1))
    first = plan(client)
    assert first["comeback"] is False
    clock["now"] = NOW + timedelta(hours=3)  # same Brussels day, now 7+ days since the last session
    second = plan(client)
    assert second["id"] != first["id"] and second["comeback"] is True
    assert {i["change"] for i in second["items"]} == {"welcome_back"}


def test_never_on_an_outdated_plan_rebuilds_it(client, clean_db, clock):
    chest_day(clean_db, NOW - timedelta(days=2))
    stale = plan(client)
    add = next(i for i in stale["items"] if i["kind"] == "add")
    client.put("/api/preferences", headers=H, json={"avoid_muscles": [add["muscle"]], "never_exercises": [], "coach_notes": ""})
    other = next((i for i in stale["items"] if i["kind"] == "add" and i["id"] != add["id"]), add)
    after = client.post(f"/api/plan/{stale['id']}/items/{other['id']}/never", headers=H).json()
    assert after["id"] != stale["id"]
    assert add["muscle"] not in {i["muscle"] for i in after["items"] if i["kind"] == "add"}


def test_no_history_is_not_a_comeback(client, clock):
    days = client.get("/api/plan/days", headers=H).json()
    assert days["comeback"] is False and days["missed_available"] is True


def test_never_list_keeps_the_latest_200(client, clean_db, clock):
    chest_day(clean_db, NOW - timedelta(days=2))
    with clean_db.begin() as c:
        c.execute(text("update profile set never_exercises = :n"), {"n": [f"Old {i}" for i in range(200)]})
    p = plan(client)
    add = next(i for i in p["items"] if i["kind"] == "add")
    client.post(f"/api/plan/{p['id']}/items/{add['id']}/never", headers=H)
    never = client.get("/api/preferences", headers=H).json()["never_exercises"]
    assert len(never) == 200 and never[-1] == add["exercise"] and "Old 0" not in never


def test_goal_exercise_must_be_known(clean_db):
    with clean_db.begin() as c:
        add_gym(c, NOW - timedelta(days=3), [(BENCH, 80, 8, "normal")], title="Push")
        out, err = execute_tool("save_goal", {"action": "create", "text": "Bench 100", "exercise": "Bench Press (Barbel)"},
                                conn=c, engine=clean_db, now=NOW)
    assert err and "Bench Press (Barbell)" in out


def test_body_goals_dont_tag_lifts(conn):
    add_gym(conn, NOW - timedelta(days=3), [("Chest Press (Machine)", 50, 10, "normal")], title="Push")
    conn.execute(text("insert into goals (text, area) values ('Chest 105 cm', 'body')"))
    assert goal_muscles(conn, NOW) == {}


def test_a_goal_naming_two_lifts_tags_both():
    from lockedin.plan.goals import goal_for
    g = [{"id": 1, "text": "Bench press 100 kg, incline bench press 40 kg", "exercise": None, "status": "active"}]
    known = ["Bench Press (Barbell)", "Incline Bench Press (Dumbbell)"]
    assert goal_for("Bench Press (Barbell)", g, known) is not None
    assert goal_for("Incline Bench Press (Dumbbell)", g, known) is not None
