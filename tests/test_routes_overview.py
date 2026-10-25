from datetime import UTC, datetime

import pytest
from conftest import SYNC_HEADERS, owner_headers, read

H = owner_headers()


@pytest.fixture(autouse=True)
def fixed_now(client):
    from lockedin.app import app
    from lockedin.routes.overview import get_now
    app.dependency_overrides[get_now] = lambda: datetime(2026, 10, 26, 12, 0, tzinfo=UTC)
    yield


def test_overview_on_empty_account(client):
    r = client.get("/api/overview", headers=H)
    assert r.status_code == 200
    o = r.json()
    assert o["totals"]["week"]["bike"] == {"time_s": 0, "distance_m": 0.0, "sessions": 0}
    assert o["comeback"]["days_since"] is None and o["focus"] == [] and o["wins"] == []
    assert o["measure_due"] is True and len(o["weekly"]) == 12 and o["streak"] == 0


def test_overview_with_imports(client):
    for name in ("zwift_ride.fit", "watch_run.fit"):
        client.post("/api/fit/upload", files={"file": (name, read(name))}, headers=SYNC_HEADERS)
    o = client.get("/api/overview?weeks=26", headers=H).json()
    assert len(o["weekly"]) == 26
    assert sum(w["bike"] for w in o["weekly"]) == 60 and sum(w["run"] for w in o["weekly"]) == 45


def test_overview_focus_mixes_gym_and_sessions(client):
    client.post("/api/hevy/upload", files={"file": ("h.csv", read("hevy_sample.csv"))}, headers=H)
    o = client.get("/api/overview", headers=H).json()
    assert o["focus"] and all(item["type"] in ("gym", "session") for item in o["focus"])
    assert o["focus"][0]["type"] == "gym" and o["focus"][0]["exercise"]


def test_overview_bad_weeks(client):
    assert client.get("/api/overview?weeks=7", headers=H).status_code == 422


def test_focus_facts_keys(client):
    f = client.get("/api/focus", headers=H).json()
    assert set(f) >= {"generated_at", "zones", "coverage", "unmapped", "gym_suggestions", "session_suggestions",
                      "mix", "plateaus", "wins", "streak", "comeback"}


def test_requires_auth(client):
    for path in ("/api/overview", "/api/focus"):
        assert client.get(path).status_code == 401
