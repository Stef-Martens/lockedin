import pytest
from conftest import owner_headers

H = owner_headers()


def test_profile_roundtrip(client):
    assert client.get("/api/profile", headers=H).json()["height_cm"] is None
    r = client.put("/api/profile", json={"date_of_birth": "1995-04-12", "height_cm": 182, "ftp_override": 240}, headers=H)
    assert r.status_code == 200
    p = client.get("/api/profile", headers=H).json()
    assert (p["date_of_birth"], p["height_cm"], p["ftp_override"], p["max_hr_override"]) == ("1995-04-12", 182, 240, None)


def test_profile_validation(client):
    assert client.put("/api/profile", json={"height_cm": 300}, headers=H).status_code == 422
    assert client.put("/api/profile", json={"max_hr_override": 90}, headers=H).status_code == 422
    assert client.put("/api/profile", json={"ftp_override": 900}, headers=H).status_code == 422


def test_measurement_crud(client):
    types = client.get("/api/measurement-types", headers=H).json()
    arm = next(t for t in types if t["name"] == "Left arm")
    r = client.post("/api/measurements", json={"type_id": arm["id"], "measured_on": "2026-10-01", "value": 35.5}, headers=H)
    assert r.status_code == 201
    client.post("/api/measurements", json={"type_id": arm["id"], "measured_on": "2026-09-01", "value": 35.0}, headers=H)
    rows = client.get(f"/api/measurements?type_id={arm['id']}", headers=H).json()
    assert [(m["measured_on"], m["value"]) for m in rows] == [("2026-09-01", 35.0), ("2026-10-01", 35.5)]
    assert client.delete(f"/api/measurements/{rows[0]['id']}", headers=H).status_code == 204
    assert len(client.get(f"/api/measurements?type_id={arm['id']}", headers=H).json()) == 1
    assert client.delete(f"/api/measurements/{rows[0]['id']}", headers=H).status_code == 404


def test_measurement_value_must_be_positive(client):
    t = client.get("/api/measurement-types", headers=H).json()[0]
    r = client.post("/api/measurements", json={"type_id": t["id"], "measured_on": "2026-10-01", "value": 0}, headers=H)
    assert r.status_code == 422


def test_measurement_unknown_type(client):
    r = client.post("/api/measurements", json={"type_id": 999, "measured_on": "2026-10-01", "value": 3}, headers=H)
    assert r.status_code == 404


def test_add_type_and_duplicate(client):
    r = client.post("/api/measurement-types", json={"name": "Calves", "unit": "cm", "kind": "tape"}, headers=H)
    assert r.status_code == 201 and r.json()["name"] == "Calves"
    dup = client.post("/api/measurement-types", json={"name": "calves", "unit": "cm", "kind": "tape"}, headers=H)
    assert dup.status_code == 409


def test_requires_auth(client):
    for path in ["/api/profile", "/api/measurement-types", "/api/measurements"]:
        assert client.get(path).status_code == 401


def test_setting_ftp_recomputes_existing_rides(client):
    from conftest import SYNC_HEADERS, read
    rid = client.post("/api/fit/upload", files={"file": ("z.fit", read("zwift_ride.fit"))}, headers=SYNC_HEADERS).json()["activity_id"]
    assert client.get(f"/api/activities/{rid}", headers=H).json()["tss"] is None
    client.put("/api/profile", json={"ftp_override": 250}, headers=H)
    assert client.get(f"/api/activities/{rid}", headers=H).json()["tss"] == pytest.approx(75.2, abs=2.5)



def test_dumbbell_logging_preference(client):
    assert client.get("/api/profile", headers=H).json()["dumbbell_weights"] == "pair"
    r = client.put("/api/profile", headers=H, json={"dumbbell_weights": "each"})
    assert r.status_code == 200 and r.json()["dumbbell_weights"] == "each"
    assert client.put("/api/profile", headers=H, json={"dumbbell_weights": "left"}).status_code == 422
