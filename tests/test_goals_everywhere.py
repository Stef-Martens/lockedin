from datetime import UTC, date, datetime, timedelta

from conftest import owner_headers
from focus_helpers import add_gym, add_session
from sqlalchemy import text

from lockedin.app import app
from lockedin.coach.tools import execute_tool
from lockedin.focus.mix import session_suggestions
from lockedin.focus.musclemap import muscle_map
from lockedin.focus.suggest import gym_suggestions
from lockedin.plan.build import build_plan
from lockedin.routes.overview import get_now

NOW = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)
BENCH, OHP = "Bench Press (Barbell)", "Overhead Press (Dumbbell)"
H = owner_headers()


def goal(conn, text_, area, exercise=None, status="active"):
    return conn.execute(text("insert into goals (text, area, exercise, status) values (:t, :a, :e, :s) returning id"),
                        {"t": text_, "a": area, "e": exercise, "s": status}).scalar_one()


def chest(conn, when, bench_sets=3):
    add_gym(conn, when, [(BENCH, 80, 8, "normal")] * bench_sets + [(OHP, 40, 10, "normal")] * 3, title="Push")


def test_goal_lift_muscles_lead_gym_suggestions(conn):
    chest(conn, datetime(2026, 10, 20, 17, tzinfo=UTC))
    goal(conn, "Bench 100 kg", "gym", BENCH)
    first = gym_suggestions(conn, NOW, limit=20)[0]
    assert first.goal == "Bench 100 kg" and first.reason.endswith("· helps: Bench 100 kg")
    assert first.muscle_key in {"mid_lower_chest", "upper_chest", "front_delt", "triceps"}


def test_run_goal_always_brings_a_run(conn):
    goal(conn, "Run a 10K", "run")
    run = [s for s in session_suggestions(conn, NOW) if s.sport == "run"]
    assert run and run[0].goal == "Run a 10K" and run[0].title == "Steady run 40′"
    assert session_suggestions(conn, NOW)[0].goal == "Run a 10K"


def test_overview_lists_goal_items_first(client, clean_db):
    app.dependency_overrides[get_now] = lambda: NOW
    with clean_db.begin() as c:
        chest(c, datetime(2026, 10, 24, 17, tzinfo=UTC))
        goal(c, "Run a 10K", "run")
    focus = client.get("/api/overview", headers=H).json()["focus"]
    assert focus[0]["goal"] == "Run a 10K"


def test_planner_adds_one_goal_set_up_to_four(conn):
    goal(conn, "Bench 100 kg", "gym", BENCH)
    chest(conn, datetime(2026, 10, 24, 17, tzinfo=UTC), bench_sets=3)
    bench = next(i for i in build_plan(conn, NOW, "Push")["items"] if i["exercise"] == BENCH)
    assert bench["sets"] == 4 and "+1 set for your goal" in bench["reason"]
    chest(conn, datetime(2026, 10, 25, 17, tzinfo=UTC), bench_sets=4)
    bench = next(i for i in build_plan(conn, NOW, "Push")["items"] if i["exercise"] == BENCH)
    assert bench["sets"] == 4


def test_no_goal_set_during_a_comeback(conn):
    goal(conn, "Bench 100 kg", "gym", BENCH)
    chest(conn, NOW - timedelta(days=12))
    bench = next(i for i in build_plan(conn, NOW, "Push")["items"] if i["exercise"] == BENCH)
    assert bench["sets"] == 3


def test_muscle_map_names_goals(conn):
    goal(conn, "Bench 100 kg", "gym", BENCH)
    m = {x["key"]: x for x in muscle_map(conn, NOW, date(2026, 10, 19))["muscles"]}
    assert m["triceps"]["goals"] == ["Bench 100 kg"] and m["quads"]["goals"] == []


def post(client, **body):
    return client.post("/api/agenda", headers=H, json=body)


def test_agenda_targets_and_goal_links(client, clean_db):
    app.dependency_overrides[get_now] = lambda: NOW
    with clean_db.begin() as c:
        gid = goal(c, "Run a 10K", "run")
        old = goal(c, "Old goal", "run", status="achieved")
    r = post(client, day="2026-10-28", sport="run", title="Steady run", goal_id=gid,
             targets={"duration_s": 2400, "pace_low": 340, "pace_high": 350, "hr_zone": 2})
    assert r.status_code == 201
    item = r.json()
    assert item["targets"]["pace_low"] == 340 and item["goal_id"] == gid and item["goal"] == "Run a 10K"
    assert post(client, day="2026-10-28", sport="bike", title="Ride", targets={"duration_s": 2400}).status_code == 422
    assert post(client, day="2026-10-28", sport="run", title="Run", targets={"pace_low": 360, "pace_high": 340}).status_code == 422
    assert post(client, day="2026-10-28", sport="swim", title="Swim", targets={"hr_zone": 2}).status_code == 422
    assert post(client, day="2026-10-28", sport="run", title="Run", goal_id=old).status_code == 422
    with clean_db.begin() as c:
        c.execute(text("delete from goals where id = :g"), {"g": gid})
    listed = client.get("/api/agenda", params={"week": "2026-10-26"}, headers=H).json()["items"]
    assert listed[0]["goal_id"] is None and listed[0]["goal"] is None


def test_coach_can_set_targets_and_goal(clean_db):
    with clean_db.begin() as c:
        gid = goal(c, "Swim 2 km", "swim")
        out, err = execute_tool("save_agenda", {"changes": [
            {"op": "add", "day": "2026-10-28", "sport": "swim", "title": "Pool 1500 m", "goal_id": gid,
             "targets": {"distance_m": 1500, "pace_low": 120, "pace_high": 130}}]}, conn=c, engine=clean_db, now=NOW)
    assert not err, out
