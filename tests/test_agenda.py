import xml.etree.ElementTree as ET
from datetime import UTC, date, datetime

import pytest
from conftest import SYNC_HEADERS, owner_headers
from focus_helpers import add_gym, add_session
from pydantic import ValidationError
from sqlalchemy import text

from lockedin.agenda.zwo import ZwiftWorkout, filename, render, summary
from lockedin.app import app
from lockedin.routes.overview import get_now

NOW = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)  # Monday
H = owner_headers()
SWEET_SPOT = {"blocks": [
    {"type": "warmup", "duration_s": 600, "from_power": 0.5, "to_power": 0.75},
    {"type": "intervals", "repeat": 3, "on_s": 600, "off_s": 300, "on_power": 0.9, "off_power": 0.55},
    {"type": "cooldown", "duration_s": 600, "from_power": 0.65, "to_power": 0.45},
]}


@pytest.fixture
def clock():
    app.dependency_overrides[get_now] = lambda: NOW


@pytest.fixture
def routine(clean_db):
    with clean_db.begin() as c:
        add_gym(c, datetime(2026, 10, 21, 17, tzinfo=UTC), [("Lat Pulldown (Cable)", 60, 10, "normal")], title="Rug - Bicep")


def post(client, **body):
    return client.post("/api/agenda", headers=H, json=body)


def week(client, d="2026-10-26"):
    return client.get("/api/agenda", params={"week": d}, headers=H).json()


# --- ZWO -------------------------------------------------------------------------------------------

def test_render_sweet_spot():
    xml = render("Sweet Spot 3x10", date(2026, 10, 29), "Seated <steady> & smooth", ZwiftWorkout(**SWEET_SPOT))
    root = ET.fromstring(xml)
    assert root.findtext("name") == "2026-10-29 Sweet Spot 3x10"
    assert root.findtext("description") == "Seated <steady> & smooth"
    assert root.findtext("sportType") == "bike" and root.findtext("author") == "LockedIn"
    blocks = list(root.find("workout"))
    assert [b.tag for b in blocks] == ["Warmup", "IntervalsT", "Cooldown"]
    assert blocks[1].attrib == {"Repeat": "3", "OnDuration": "600", "OffDuration": "300", "OnPower": "0.9", "OffPower": "0.55"}
    assert blocks[2].attrib == {"Duration": "600", "PowerLow": "0.65", "PowerHigh": "0.45"}


def test_filenames_are_safe():
    name = filename("../../evil/x", date(2026, 10, 29))
    assert "/" not in name and "\\" not in name and not name.startswith(".") and name.endswith(".zwo")
    assert name.startswith("2026-10-29 ")
    long = filename("x" * 200, date(2026, 10, 29))
    assert len(long) <= 84


@pytest.mark.parametrize("blocks", [
    [{"type": "steady", "duration_s": 600, "power": 5}],
    [{"type": "steady", "duration_s": -5, "power": 0.6}],
    [{"type": "steady", "duration_s": 60, "power": 0.6}] * 31,
    [{"type": "steady", "duration_s": 14400, "power": 0.6}, {"type": "steady", "duration_s": 10800, "power": 0.6}],
    [{"type": "sprint", "duration_s": 60}],
    [],
])
def test_bad_blocks_are_rejected(blocks):
    with pytest.raises(ValidationError):
        ZwiftWorkout(blocks=blocks)


def test_summary_in_watts_or_percent():
    w = ZwiftWorkout(**SWEET_SPOT)
    assert summary(w, 168) == "65′ · 3 × 10′ at 151 W"
    assert summary(w, None) == "65′ · 3 × 10′ at 90%"
    steady = ZwiftWorkout(blocks=[{"type": "steady", "duration_s": 3600, "power": 0.68}])
    assert summary(steady, 168) == "60′ · 60′ at 114 W"


# --- API -------------------------------------------------------------------------------------------

def test_gym_routine_must_exist(client, clock, routine):
    r = post(client, day="2026-10-27", sport="gym", title="Back day", routine="Leg day")
    assert r.status_code == 422 and "Rug - Bicep" in r.text
    r = post(client, day="2026-10-27", sport="gym", title="Rug - Bicep", routine="Rug - Bicep")
    assert r.status_code == 201 and r.json()["source"] == "manual"


def test_zwift_item_lifecycle(client, clock):
    r = post(client, day="2026-10-29", sport="bike", title="Sweet Spot 3x10", zwift=SWEET_SPOT)
    assert r.status_code == 201
    item = r.json()
    assert item["zwift_status"] == "pending" and item["zwift"]["duration_s"] == 3900
    client.post("/api/agenda/zwift/confirm", headers=SYNC_HEADERS, json={"item_ids": [item["id"]]})
    assert week(client)["items"][0]["zwift_status"] == "synced"
    moved = client.patch(f"/api/agenda/{item['id']}", headers=H, json={"day": "2026-10-30"}).json()
    assert moved["day"] == "2026-10-30" and moved["zwift_status"] == "pending"
    assert client.delete(f"/api/agenda/{item['id']}", headers=H).status_code == 204
    assert week(client)["items"] == []
    assert client.patch(f"/api/agenda/{item['id']}", headers=H, json={"day": "2026-10-30"}).status_code == 404


def test_zwift_blocks_only_on_bike(client, clock):
    assert post(client, day="2026-10-28", sport="run", title="Run", zwift=SWEET_SPOT).status_code == 422
    assert post(client, day="2026-10-28", sport="run", title="").status_code == 422


def test_week_snaps_to_monday_and_sorts(client, clock):
    post(client, day="2026-10-30", sport="rest", title="Rest")
    post(client, day="2026-10-27", sport="run", title="Easy run", note="Zone 2")
    post(client, day="2026-11-02", sport="run", title="Next week")
    w = week(client, "2026-10-29")
    assert w["week_start"] == "2026-10-26" and w["today"] == "2026-10-26"
    assert [i["title"] for i in w["items"]] == ["Easy run", "Rest"]


def test_tick_off(client, clean_db, clock, routine):
    post(client, day="2026-10-21", sport="gym", title="Any gym")
    post(client, day="2026-10-21", sport="gym", title="Rug - Bicep", routine="Rug - Bicep")
    post(client, day="2026-10-22", sport="bike", title="Ride A")
    post(client, day="2026-10-22", sport="bike", title="Ride B")
    post(client, day="2026-10-23", sport="rest", title="Rest")
    post(client, day="2026-10-25", sport="bike", title="Sunday ride")
    with clean_db.begin() as c:
        ride = add_session(c, "bike", datetime(2026, 10, 22, 17, tzinfo=UTC), 3600, source="zwift")
        add_session(c, "bike", datetime(2026, 10, 25, 22, 30, tzinfo=UTC), 3600, source="zwift")  # Sun 23:30 Brussels
    items = {i["title"]: i for i in week(client, "2026-10-19")["items"]}
    assert items["Rug - Bicep"]["done"] is True and items["Any gym"]["done"] is False
    assert items["Ride A"]["done"] is True and items["Ride A"]["activity_id"] == ride
    assert items["Ride B"]["done"] is False and items["Rest"]["done"] is False
    assert items["Sunday ride"]["done"] is True
    assert items["Ride A"]["zwift_status"] is None  # past days have no Zwift status


def test_zwift_feed(client, clock):
    post(client, day="2026-10-25", sport="bike", title="Yesterday", zwift=SWEET_SPOT)
    post(client, day="2026-10-26", sport="bike", title="Recovery Spin 30",
         zwift={"blocks": [{"type": "steady", "duration_s": 1800, "power": 0.6}]})
    post(client, day="2026-10-29", sport="bike", title="Sweet Spot 3x10", zwift=SWEET_SPOT)
    post(client, day="2026-10-29", sport="bike", title="No file, just a note")
    feed = client.post("/api/agenda/zwift/sync", headers=SYNC_HEADERS).json()
    assert [f["filename"] for f in feed] == ["2026-10-26 Recovery Spin 30.zwo", "2026-10-29 Sweet Spot 3x10.zwo"]
    assert ET.fromstring(feed[1]["content"]).findtext("name") == "2026-10-29 Sweet Spot 3x10"
    assert client.post("/api/agenda/zwift/sync", headers=H).status_code == 401
    assert client.post("/api/agenda/zwift/sync").status_code == 401


def test_in_zwift_only_after_the_mac_confirms(client, clock):
    item = post(client, day="2026-10-29", sport="bike", title="Sweet Spot 3x10", zwift=SWEET_SPOT).json()
    client.post("/api/agenda/zwift/sync", headers=SYNC_HEADERS)
    assert week(client)["items"][0]["zwift_status"] == "pending"  # served isn't the same as written
    r = client.post("/api/agenda/zwift/confirm", headers=SYNC_HEADERS, json={"item_ids": [item["id"], 99999]})
    assert r.status_code == 200
    assert week(client)["items"][0]["zwift_status"] == "synced"
    assert client.post("/api/agenda/zwift/confirm", headers=H, json={"item_ids": []}).status_code == 401


def test_feed_file_names_are_unique_ignoring_case(client, clock):
    for title in ("Z2 ride", "Z2 ride", "z2 RIDE"):
        post(client, day="2026-10-29", sport="bike", title=title, zwift=SWEET_SPOT)
    names = [f["filename"] for f in client.post("/api/agenda/zwift/sync", headers=SYNC_HEADERS).json()]
    assert len({n.lower() for n in names}) == 3
    assert names[0] == "2026-10-29 Z2 ride.zwo"


@pytest.mark.parametrize("method, path", [
    ("get", "/api/agenda"), ("post", "/api/agenda"), ("patch", "/api/agenda/1"), ("delete", "/api/agenda/1"),
])
def test_requires_owner(client, method, path):
    assert getattr(client, method)(path).status_code == 401
    assert getattr(client, method)(path, headers=SYNC_HEADERS).status_code == 401


def test_coach_can_read_agenda(clean_db):
    with clean_db.begin() as c:
        assert c.execute(text("select has_table_privilege('coach_ro', 'agenda_items', 'select')")).scalar()


def test_a_renamed_gym_workout_still_ticks_its_day(client, clean_db, clock):
    with clean_db.begin() as c:
        add_gym(c, datetime(2026, 10, 20, 17, tzinfo=UTC), [("Bench Press (Barbell)", 80, 8, "normal")], title="Chest - Schouders - Triceps")
    post(client, day="2026-10-21", sport="gym", title="Chest - Schouders - Triceps", routine="Chest - Schouders - Triceps")
    with clean_db.begin() as c:
        gym = add_gym(c, datetime(2026, 10, 21, 6, 56, tzinfo=UTC), [("Bench Press (Barbell)", 82.5, 5, "normal")],
                      title="Chest - shoulder - tricep")
    item = week(client, "2026-10-19")["items"][0]
    assert item["done"] is True and item["activity_id"] == gym


def test_a_renamed_workout_beats_an_earlier_unplanned_one_that_day(client, clean_db, clock):
    """An extra ab session before the planned (but renamed) chest day: the chest workout ticks the chest item."""
    with clean_db.begin() as c:
        add_gym(c, datetime(2026, 10, 20, 17, tzinfo=UTC),
                [("Bench Press (Barbell)", 80, 8, "normal"), ("Lateral Raise (Dumbbell)", 28, 10, "normal")],
                title="Chest - Schouders - Triceps")
    post(client, day="2026-10-21", sport="gym", title="Chest - Schouders - Triceps", routine="Chest - Schouders - Triceps")
    with clean_db.begin() as c:
        add_gym(c, datetime(2026, 10, 21, 6, 20, tzinfo=UTC), [("Bicycle Crunch", 0, 20, "normal")], title="Buik")
        chest = add_gym(c, datetime(2026, 10, 21, 9, 43, tzinfo=UTC),
                        [("Bench Press (Barbell)", 70, 7, "normal"), ("Lateral Raise (Dumbbell)", 28, 9, "normal")],
                        title="Chest - shoulder - tricep")
    item = week(client, "2026-10-19")["items"][0]
    assert item["activity_id"] == chest


def test_the_routine_named_workout_wins(client, clean_db, clock):
    with clean_db.begin() as c:
        for t in ("Push", "Pull"):
            add_gym(c, datetime(2026, 10, 20, 17, tzinfo=UTC) if t == "Push" else datetime(2026, 10, 19, 17, tzinfo=UTC),
                    [("Bench Press (Barbell)", 80, 8, "normal")], title=t)
    post(client, day="2026-10-22", sport="gym", title="Push", routine="Push")
    post(client, day="2026-10-22", sport="gym", title="Pull", routine="Pull")
    with clean_db.begin() as c:
        pull = add_gym(c, datetime(2026, 10, 22, 17, tzinfo=UTC), [("Lat Pulldown (Cable)", 60, 10, "normal")], title="Pull")
    items = {i["title"]: i for i in week(client, "2026-10-19")["items"]}
    assert items["Pull"]["activity_id"] == pull and items["Push"]["done"] is False


def test_a_ride_on_a_rest_day_ticks_it(client, clean_db, clock):
    post(client, day="2026-10-20", sport="rest", title="Rest", note="Optional: easy 20–30 min spin under 126 W")
    post(client, day="2026-10-22", sport="bike", title="Sweet Spot")
    post(client, day="2026-10-22", sport="rest", title="Rest")
    with clean_db.begin() as c:
        spin = add_session(c, "bike", datetime(2026, 10, 20, 18, 59, tzinfo=UTC), 1808, source="zwift", avg_power=88)
        add_session(c, "bike", datetime(2026, 10, 22, 17, tzinfo=UTC), 3600, source="zwift")
    items = week(client, "2026-10-19")["items"]
    monday = next(i for i in items if i["day"] == "2026-10-20")
    assert monday["done"] is True and monday["activity_id"] == spin
    thursday = {i["sport"]: i for i in items if i["day"] == "2026-10-22"}
    assert thursday["bike"]["done"] is True and thursday["rest"]["done"] is False  # the ride belongs to the planned ride
    lines = client.get(f"/api/agenda/{monday['id']}/detail", headers=H).json()["item"]["result"]
    assert lines == "Done · 30′ · 88 W"
