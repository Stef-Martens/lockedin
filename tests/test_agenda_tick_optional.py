from datetime import UTC, datetime

import pytest
from conftest import owner_headers
from focus_helpers import add_session

from lockedin.app import app
from lockedin.routes.overview import get_now

H = owner_headers()


@pytest.fixture
def clock():
    app.dependency_overrides[get_now] = lambda: datetime(2026, 10, 26, 12, 0, tzinfo=UTC)


def test_one_ride_ticks_the_main_ride_before_the_optional_one(client, clean_db, clock):
    for body in ({"title": "Easy spin", "optional": True, "sort": 0}, {"title": "Sweet Spot", "sort": 1}):
        r = client.post("/api/agenda", headers=H, json={"day": "2026-10-22", "sport": "bike", **body})
        assert r.status_code == 201, r.text
    with clean_db.begin() as c:
        ride = add_session(c, "bike", datetime(2026, 10, 22, 17, tzinfo=UTC), 3600, source="zwift")
    items = {i["title"]: i for i in client.get("/api/agenda", params={"week": "2026-10-19"}, headers=H).json()["items"]}
    assert items["Sweet Spot"]["done"] is True and items["Sweet Spot"]["activity_id"] == ride
    assert items["Easy spin"]["done"] is False
