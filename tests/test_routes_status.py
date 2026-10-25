from conftest import SYNC_HEADERS, owner_headers, read

H = owner_headers()


def test_status_empty(client):
    s = client.get("/api/status", headers=H).json()
    assert s["zwift"] == {"last_import_at": None, "count": 0}
    assert s["last_tape_measurement_on"] is None


def test_status_after_imports(client):
    client.post("/api/fit/upload", files={"file": ("z.fit", read("zwift_ride.fit"))}, headers=SYNC_HEADERS)
    client.post("/api/fit/upload", files={"file": ("r.fit", read("watch_run.fit"))}, headers=SYNC_HEADERS)
    client.post("/api/hevy/upload", files={"file": ("h.csv", read("hevy_sample.csv"))}, headers=H)
    types = client.get("/api/measurement-types", headers=H).json()
    weight = next(t for t in types if t["kind"] == "weight")
    chest = next(t for t in types if t["name"] == "Chest")
    client.post("/api/measurements", json={"type_id": chest["id"], "measured_on": "2026-09-15", "value": 100}, headers=H)
    client.post("/api/measurements", json={"type_id": weight["id"], "measured_on": "2026-10-20", "value": 80}, headers=H)
    s = client.get("/api/status", headers=H).json()
    assert (s["zwift"]["count"], s["healthfit"]["count"], s["hevy"]["count"]) == (1, 1, 3)
    assert all(s[k]["last_import_at"] for k in ("zwift", "healthfit", "hevy"))
    assert s["last_tape_measurement_on"] == "2026-09-15"  # weight is not a tape measurement


def test_requires_auth(client):
    assert client.get("/api/status").status_code == 401
