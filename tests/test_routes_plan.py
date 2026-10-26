from datetime import UTC, datetime, timedelta

import pytest
from conftest import owner_headers
from focus_helpers import add_gym
from sqlalchemy import text

from lockedin.app import app
from lockedin.routes.overview import get_now

NOW = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)
H = owner_headers()
CHEST = "Chest - Schouders - Triceps"
BENCH, INCLINE, OHP = "Bench Press (Barbell)", "Incline Bench Press (Dumbbell)", "Overhead Press (Dumbbell)"


@pytest.fixture
def clock():
    state = {"now": NOW}
    app.dependency_overrides[get_now] = lambda: state["now"]
    return state


def chest_day(engine, when):
    with engine.begin() as c:
        add_gym(c, when, [(BENCH, 60, 8, "normal")] * 3 + [(INCLINE, 50, 10, "normal")] * 3
                + [(OHP, 40, 10, "normal")] * 3, title=CHEST)


def get_plan(client, day=CHEST):
    r = client.get("/api/plan", params={"day": day} if day else {}, headers=H)
    assert r.status_code == 200, r.text
    return r.json()


def test_days_and_goals(client, clean_db, clock):
    chest_day(clean_db, datetime(2026, 10, 24, 17, tzinfo=UTC))
    with clean_db.begin() as c:
        c.execute(text("insert into goals (text, target, status) values ('Bench 100 kg', 'by March', 'active'), "
                       "('Old one', null, 'achieved')"))
    days = client.get("/api/plan/days", headers=H).json()
    assert days["days"] == [{"title": CHEST, "last_done": "2026-10-24", "exercise_count": 3}]
    assert days["missed_available"] is True and days["comeback"] is False
    assert [g["text"] for g in days["goals"]] == ["Bench 100 kg"]
    assert [g["text"] for g in client.get("/api/goals/active", headers=H).json()] == ["Bench 100 kg"]


def test_plan_is_saved_and_reused_the_same_day(client, clean_db, clock):
    chest_day(clean_db, datetime(2026, 10, 24, 17, tzinfo=UTC))
    first = get_plan(client)
    assert [i["exercise"] for i in first["items"]][:3] == [BENCH, INCLINE, OHP]
    assert get_plan(client)["id"] == first["id"]
    assert client.post("/api/plan/new", params={"day": CHEST}, headers=H).json()["id"] != first["id"]


def test_plan_refreshes_on_a_new_day(client, clean_db, clock):
    chest_day(clean_db, datetime(2026, 10, 24, 17, tzinfo=UTC))
    first = get_plan(client)
    clock["now"] = NOW + timedelta(days=1)
    assert get_plan(client)["id"] != first["id"]


def test_plan_refreshes_after_a_newer_workout(client, clean_db, clock):
    chest_day(clean_db, datetime(2026, 10, 24, 17, tzinfo=UTC))
    first = get_plan(client)
    chest_day(clean_db, datetime(2026, 10, 26, 8, tzinfo=UTC))
    assert get_plan(client)["id"] != first["id"]


def test_plan_refreshes_when_preferences_change(client, clean_db, clock):
    chest_day(clean_db, datetime(2026, 10, 24, 17, tzinfo=UTC))
    first = get_plan(client)
    added = {i["muscle"] for i in first["items"] if i["kind"] == "add"}
    assert "rear_delt" in added
    client.put("/api/preferences", headers=H, json={"avoid_muscles": ["rear_delt"], "never_exercises": [], "coach_notes": ""})
    second = get_plan(client)
    assert second["id"] != first["id"]
    assert "rear_delt" not in {i["muscle"] for i in second["items"] if i["kind"] == "add"}


def test_actions_apply_by_item_id(client, clean_db, clock):
    chest_day(clean_db, datetime(2026, 10, 24, 17, tzinfo=UTC))
    plan = get_plan(client)
    bench, add = plan["items"][0], next(i for i in plan["items"] if i["kind"] == "add")
    skipped = client.post(f"/api/plan/{plan['id']}/items/{bench['id']}/skip", headers=H).json()
    swapped = client.post(f"/api/plan/{plan['id']}/items/{add['id']}/swap", headers=H).json()
    by_id = {i["id"]: i for i in swapped["items"]}
    assert by_id[bench["id"]]["skipped"] is True and skipped["id"] == plan["id"]
    assert by_id[add["id"]]["exercise"] != add["exercise"] and by_id[add["id"]]["muscle"] == add["muscle"]
    assert get_plan(client)["items"] == swapped["items"]  # stored
    unskipped = client.post(f"/api/plan/{plan['id']}/items/{bench['id']}/skip", headers=H).json()
    assert next(i for i in unskipped["items"] if i["id"] == bench["id"])["skipped"] is False


def test_never_only_on_suggested_items(client, clean_db, clock):
    chest_day(clean_db, datetime(2026, 10, 24, 17, tzinfo=UTC))
    plan = get_plan(client)
    bench, add = plan["items"][0], next(i for i in plan["items"] if i["kind"] == "add")
    assert client.post(f"/api/plan/{plan['id']}/items/{bench['id']}/never", headers=H).status_code == 400
    after = client.post(f"/api/plan/{plan['id']}/items/{add['id']}/never", headers=H).json()
    assert add["exercise"] in client.get("/api/preferences", headers=H).json()["never_exercises"]
    assert next(i for i in after["items"] if i["id"] == add["id"])["exercise"] != add["exercise"]
    assert get_plan(client)["id"] == plan["id"]  # the plan already reflects the new preference


def test_errors(client, clean_db, clock):
    assert client.get("/api/plan", params={"day": "Nope"}, headers=H).status_code == 404
    chest_day(clean_db, NOW - timedelta(days=12))
    assert client.get("/api/plan", headers=H).status_code == 409  # "missed" is hidden during a comeback
    plan = get_plan(client)
    assert client.post(f"/api/plan/{plan['id']}/items/zzz/skip", headers=H).status_code == 404
    assert client.post(f"/api/plan/999999/items/{plan['items'][0]['id']}/skip", headers=H).status_code == 404


@pytest.mark.parametrize("method, path", [
    ("get", "/api/plan/days"), ("get", "/api/plan"), ("post", "/api/plan/new"), ("get", "/api/goals/active"),
    ("post", "/api/plan/1/items/x/swap"), ("post", "/api/plan/1/items/x/skip"), ("post", "/api/plan/1/items/x/never"),
])
def test_requires_owner(client, method, path):
    assert getattr(client, method)(path).status_code == 401


def test_never_without_an_alternative_still_saves_and_drops_the_extra(client, clean_db, clock):
    chest_day(clean_db, datetime(2026, 10, 24, 17, tzinfo=UTC))
    plan = get_plan(client)
    add = next(i for i in plan["items"] if i["kind"] == "add" and i["muscle"] == "rear_delt")
    names = []
    for _ in range(3):  # three rear-delt exercises in the library; the third "never" has nothing left to offer
        current = next((i for i in get_plan(client)["items"] if i["id"] == add["id"]), None)
        if current is None:
            break
        names.append(current["exercise"])
        r = client.post(f"/api/plan/{plan['id']}/items/{add['id']}/never", headers=H)
        assert r.status_code == 200, r.text
    assert set(names) <= set(client.get("/api/preferences", headers=H).json()["never_exercises"])
    assert all(i["id"] != add["id"] for i in get_plan(client)["items"])
