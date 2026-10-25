from datetime import UTC, datetime

import pytest
from conftest import owner_headers

H = owner_headers()


@pytest.fixture
def types(client):
    return {t["name"]: t["id"] for t in client.get("/api/measurement-types", headers=H).json()}


def test_batch_save_skips_blanks(client, types):
    body = {"measured_on": "2026-10-26", "values": {str(types["Weight"]): 78.4, str(types["Chest"]): 101.5,
                                                    str(types["Waist"]): 82, str(types["Hips"]): None, str(types["Left arm"]): 0}}
    r = client.post("/api/checkins", json=body, headers=H)
    assert r.status_code == 201 and r.json() == {"measured_on": "2026-10-26", "saved": 3}


def test_resaving_a_date_replaces_values(client, types):
    w = str(types["Weight"])
    client.post("/api/checkins", json={"measured_on": "2026-10-26", "values": {w: 78.4}}, headers=H)
    client.post("/api/checkins", json={"measured_on": "2026-10-26", "values": {w: 78.1}}, headers=H)
    rows = client.get(f"/api/measurements?type_id={w}", headers=H).json()
    assert [(m["measured_on"], m["value"]) for m in rows] == [("2026-10-26", pytest.approx(78.1))]


def test_empty_checkin_is_rejected(client, types):
    r = client.post("/api/checkins", json={"measured_on": "2026-10-26", "values": {str(types["Chest"]): None}}, headers=H)
    assert r.status_code == 422 and r.json()["detail"] == "Fill in at least one measurement."


def test_unknown_type(client):
    r = client.post("/api/checkins", json={"measured_on": "2026-10-26", "values": {"9999": 3}}, headers=H)
    assert r.status_code == 404


def test_history_grouped_newest_first(client, types):
    w, c = str(types["Weight"]), str(types["Chest"])
    client.post("/api/checkins", json={"measured_on": "2026-10-12", "values": {w: 79, c: 100}}, headers=H)
    client.post("/api/checkins", json={"measured_on": "2026-10-26", "values": {w: 78.4}}, headers=H)
    h = client.get("/api/checkins", headers=H).json()
    assert [x["measured_on"] for x in h] == ["2026-10-26", "2026-10-12"]
    assert h[1]["values"] == {w: 79.0, c: 100.0}


def test_reminder_profile_fields(client):
    p = client.get("/api/profile", headers=H).json()
    assert (p["reminder_weeks"], p["reminder_hevy"]) == (2, True)
    r = client.put("/api/profile", headers=H, json={"reminder_weeks": 4, "reminder_hevy": False})
    assert (r.json()["reminder_weeks"], r.json()["reminder_hevy"]) == (4, False)
    assert client.put("/api/profile", headers=H, json={"reminder_weeks": 3}).status_code == 422


def test_requires_auth(client):
    assert client.get("/api/checkins").status_code == 401
    assert client.post("/api/checkins", json={}).status_code == 401
    assert client.get("/api/reminders/calendar.ics").status_code == 401


def test_patch_profile_only_touches_sent_fields(client):
    client.put("/api/profile", headers=H, json={"ftp_override": 240, "height_cm": 182, "date_of_birth": "1995-04-12"})
    r = client.patch("/api/profile", headers=H, json={"reminder_weeks": 4})
    p = r.json()
    assert r.status_code == 200 and (p["reminder_weeks"], p["ftp_override"], p["height_cm"], p["date_of_birth"]) == (4, 240, 182, "1995-04-12")
    assert client.patch("/api/profile", headers=H, json={"reminder_weeks": 3}).status_code == 422


def test_delete_a_checkin(client, types):
    w, c = str(types["Weight"]), str(types["Chest"])
    client.post("/api/checkins", json={"measured_on": "2026-10-12", "values": {w: 79}}, headers=H)
    client.post("/api/checkins", json={"measured_on": "2026-10-26", "values": {w: 78.4, c: 101}}, headers=H)
    assert client.delete("/api/checkins/2026-10-26", headers=H).status_code == 204
    assert [x["measured_on"] for x in client.get("/api/checkins", headers=H).json()] == ["2026-10-12"]
    assert client.delete("/api/checkins/2026-10-26", headers=H).status_code == 404


def test_resave_keeps_other_types_on_that_date(client, types):
    w, c = str(types["Weight"]), str(types["Chest"])
    client.post("/api/checkins", json={"measured_on": "2026-10-26", "values": {w: 78.4, c: 101}}, headers=H)
    client.post("/api/checkins", json={"measured_on": "2026-10-26", "values": {w: 78.0}}, headers=H)
    assert client.get("/api/checkins", headers=H).json()[0]["values"] == {w: 78.0, c: 101.0}


@pytest.mark.parametrize("bad", [7840, 1000, float("inf")])
def test_implausible_values_rejected(client, types, bad):
    body = {"measured_on": "2026-10-26", "values": {str(types["Weight"]): bad}}
    r = client.post("/api/checkins", content=__import__("json").dumps(body, allow_nan=True), headers={**H, "Content-Type": "application/json"})
    assert r.status_code == 422


def test_future_date_rejected(client, types):
    from lockedin.app import app
    from lockedin.routes.overview import get_now
    app.dependency_overrides[get_now] = lambda: datetime(2026, 10, 26, 9, 0, tzinfo=UTC)
    r = client.post("/api/checkins", json={"measured_on": "2026-10-27", "values": {str(types["Weight"]): 78}}, headers=H)
    assert r.status_code == 422
