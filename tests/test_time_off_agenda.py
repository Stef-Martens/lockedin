from datetime import UTC, date, datetime, timedelta

import pytest
from conftest import owner_headers
from focus_helpers import add_gym

from lockedin import timeoff
from lockedin.agenda.store import ItemIn, create, zwift_feed
from lockedin.app import app
from lockedin.coach.tools import execute_tool
from lockedin.routes.overview import get_now
from lockedin.timeoff import Restriction, TimeOffIn

H = owner_headers()
NOW = datetime(2026, 12, 1, 12, 0, tzinfo=UTC)  # Tuesday
BENCH, SQUAT, LEG_PRESS = "Bench Press (Barbell)", "Squat (Barbell)", "Leg Press Horizontal (Machine)"
SWEET_SPOT = {"blocks": [{"type": "steady", "duration_s": 3600, "power": 0.7}]}


@pytest.fixture
def clock():
    app.dependency_overrides[get_now] = lambda: NOW


def off(conn, start=date(2026, 12, 1), **until):
    return timeoff.create(conn, TimeOffIn(reason="injury", label="Knee operation", start=start, restrictions=[
        Restriction(category=c, until=u) for c, u in until.items()]))


def post(client, **body):
    return client.post("/api/agenda", headers=H, json=body)


def save(engine, changes):
    with engine.begin() as c:
        return execute_tool("save_agenda", {"changes": changes}, conn=c, engine=engine, now=NOW)


def test_coach_cannot_plan_a_restricted_activity(clean_db, clock):
    with clean_db.begin() as c:
        off(c, run=date(2026, 12, 17))
    out, err = save(clean_db, [{"op": "add", "day": "2026-12-10", "sport": "run", "title": "Easy run"}])
    assert err and "Running is off until 17 Dec, so I can't plan it then." in out
    out, err = save(clean_db, [{"op": "add", "day": "2026-12-18", "sport": "run", "title": "Easy run"}])  # first day back
    assert not err
    out, err = save(clean_db, [{"op": "add", "day": "2026-12-10", "sport": "bike", "title": "Ride"}])
    assert not err


def test_coach_cannot_move_an_item_into_time_off(clean_db, clock):
    with clean_db.begin() as c:
        off(c, run=date(2026, 12, 17))
        item = create(c, NOW, ItemIn(day=date(2026, 12, 20), sport="run", title="Easy run"), "coach")["id"]
    out, err = save(clean_db, [{"op": "update", "id": item, "day": "2026-12-10"}])
    assert err and "Running is off until 17 Dec, so I can't plan it then." in out
    out, err = save(clean_db, [{"op": "update", "id": item, "note": "Zone 2"}])
    assert not err


def test_manual_add_succeeds_with_a_clash(client, clean_db, clock):
    with clean_db.begin() as c:
        off(c, run=date(2026, 12, 17))
    r = post(client, day="2026-12-10", sport="run", title="Easy run")
    assert r.status_code == 201 and r.json()["clash"] == "Running is off until 17 Dec"
    assert post(client, day="2026-12-10", sport="bike", title="Ride").json()["clash"] is None
    assert post(client, day="2026-12-18", sport="run", title="Run").json()["clash"] is None


def test_existing_items_are_flagged_not_deleted(client, clean_db, clock):
    item = post(client, day="2026-12-10", sport="run", title="Easy run").json()
    assert item["clash"] is None
    with clean_db.begin() as c:
        off(c, run=date(2026, 12, 17))
    items = client.get("/api/agenda", params={"week": "2026-12-07"}, headers=H).json()["items"]
    assert [(i["id"], i["clash"]) for i in items] == [(item["id"], "Running is off until 17 Dec")]


def test_week_lists_days_inside_time_off(client, clean_db, clock):
    with clean_db.begin() as c:
        off(c, start=date(2026, 12, 3), run=date(2026, 12, 4), upper=date(2026, 12, 5))
    days = client.get("/api/agenda", params={"week": "2026-12-01"}, headers=H).json()["time_off"]
    assert days == [
        {"day": "2026-12-03", "reason": "injury", "label": "Knee operation", "text": "no running, no upper body"},
        {"day": "2026-12-04", "reason": "injury", "label": "Knee operation", "text": "no running, no upper body"},
        {"day": "2026-12-05", "reason": "injury", "label": "Knee operation", "text": "no upper body"},
    ]


def test_zwift_feed_skips_bike_off_days(clean_db):
    with clean_db.begin() as c:
        for d in (4, 5, 8):
            create(c, NOW, ItemIn(day=date(2026, 12, d), sport="bike", title=f"Ride {d}", zwift=SWEET_SPOT), "coach")
        off(c, start=date(2026, 12, 5), bike=date(2026, 12, 6))
        assert [f["filename"][:10] for f in zwift_feed(c, NOW)] == ["2026-12-04", "2026-12-08"]


def test_no_zwift_pill_for_a_ride_on_a_bike_off_day(client, clean_db, clock):
    with clean_db.begin() as c:
        off(c, start=date(2026, 12, 5), bike=date(2026, 12, 6))
    off_day = post(client, day="2026-12-05", sport="bike", title="Ride", zwift=SWEET_SPOT).json()
    fine_day = post(client, day="2026-12-08", sport="bike", title="Ride", zwift=SWEET_SPOT).json()
    assert off_day["clash"] == "Cycling is off until 6 Dec" and off_day["zwift_status"] is None
    assert fine_day["zwift_status"] == "pending"


def test_gym_routine_mostly_chest_clashes_with_upper_body(clean_db):
    with clean_db.begin() as c:
        add_gym(c, NOW - timedelta(days=3), [(BENCH, 60, 8, "normal")] * 7 + [(SQUAT, 80, 8, "normal")] * 3, title="Chest")
        add_gym(c, NOW - timedelta(days=4), [(BENCH, 60, 8, "normal")] * 5 + [(SQUAT, 80, 8, "normal")] * 5, title="Mixed")
        off(c, upper=date(2027, 1, 2))
    out, err = save(clean_db, [{"op": "add", "day": "2026-12-03", "sport": "gym", "title": "Chest", "routine": "Chest"}])
    assert err and "Upper body is off until 2 Jan, so I can't plan it then." in out
    out, err = save(clean_db, [{"op": "add", "day": "2026-12-03", "sport": "gym", "title": "Mixed", "routine": "Mixed"}])
    assert not err  # exactly half is not more than half
    with clean_db.begin() as c:
        upper = timeoff.off_on(c, date(2026, 12, 3))
        assert timeoff.item_clash(c, upper, {"sport": "gym", "routine": "Chest"}) == "Upper body is off until 2 Jan"
        assert timeoff.item_clash(c, upper, {"sport": "gym", "routine": "Mixed"}) is None
        assert timeoff.item_clash(c, upper, {"sport": "gym", "routine": None}) is None
        assert timeoff.item_clash(c, upper, {"sport": "swim", "routine": None}) is None
        assert timeoff.item_clash(c, upper, {"sport": "rest", "routine": None}) is None


def test_gym_clash_counts_every_region_that_is_off(clean_db):
    with clean_db.begin() as c:
        add_gym(c, NOW - timedelta(days=4), [(BENCH, 60, 8, "normal")] * 5 + [(LEG_PRESS, 80, 8, "normal")] * 5,
                title="Mixed")
        off(c, upper=date(2027, 1, 2), lower=date(2026, 12, 20))
    out, err = save(clean_db, [{"op": "add", "day": "2026-12-03", "sport": "gym", "title": "Mixed", "routine": "Mixed"}])
    assert err and "Upper body is off until 2 Jan, so I can't plan it then." in out
    with clean_db.begin() as c:
        off(c, core=date(2026, 12, 10))
        every_part = timeoff.off_on(c, date(2026, 12, 3))
        assert timeoff.item_clash(c, every_part, {"sport": "gym", "routine": None}) == "The gym is off until 10 Dec"


def test_away_rules_out_every_gym_item(client, clean_db, clock):
    with clean_db.begin() as c:
        add_gym(c, NOW - timedelta(days=4), [(BENCH, 60, 8, "normal")] * 5 + [(SQUAT, 80, 8, "normal")] * 5, title="Mixed")
        timeoff.create(c, TimeOffIn(reason="vacation", start=date(2026, 12, 5),
                                    restrictions=[Restriction(category="all", until=date(2026, 12, 12))]))
    for routine in ("Mixed", None):
        out, err = save(clean_db, [{"op": "add", "day": "2026-12-08", "sport": "gym", "title": "Gym", "routine": routine}])
        assert err and "Everything is off until 12 Dec, so I can't plan it then." in out
    item = post(client, day="2026-12-08", sport="gym", title="Gym").json()
    assert item["clash"] == "Everything is off until 12 Dec"
    assert post(client, day="2026-12-08", sport="run", title="Run").json()["clash"] == "Running is off until 12 Dec"


def test_first_two_weeks_back_are_easy(client, clean_db, clock):
    with clean_db.begin() as c:
        off(c, start=date(2026, 11, 1), run=date(2026, 11, 20))
    note = "First two weeks back after your time off: keep it easy."
    for day, expected in (("2026-11-21", note), ("2026-12-04", note), ("2026-12-05", None), ("2026-11-20", None)):
        item = post(client, day=day, sport="run", title="Run").json()
        got = client.get(f"/api/agenda/{item['id']}/detail", headers=H).json()
        assert got["easy_back"] == expected, day
    ride = post(client, day="2026-11-22", sport="bike", title="Ride").json()
    assert client.get(f"/api/agenda/{ride['id']}/detail", headers=H).json()["easy_back"] is None