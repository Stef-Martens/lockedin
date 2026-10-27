"""Saving and editing runs with steps, through the API."""

from datetime import UTC, datetime

import pytest
from conftest import owner_headers
from test_run_steps import TEMPO

from lockedin.app import app
from lockedin.routes.overview import get_now

NOW = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)  # Monday
H = owner_headers()
LINE = "10′ warm-up Z2 · 4 × (5′ @ 5:30–5:50, 2′ jog) · cool-down"


@pytest.fixture
def clock():
    app.dependency_overrides[get_now] = lambda: NOW


def run_with(client, targets):
    r = client.post("/api/agenda", headers=H, json={"day": "2026-10-28", "sport": "run", "title": "Run", "targets": targets})
    assert r.status_code == 201, r.text
    return r.json()


def patch(client, item, **body):
    return client.patch(f"/api/agenda/{item['id']}", headers=H, json=body)


def test_create_run_with_steps(client, clock):
    item = run_with(client, {"steps": TEMPO})
    assert item["targets"]["steps"] == TEMPO
    assert item["targets"]["pace_low"] == 330
    assert item["plan_line"] == LINE


def test_patch_without_steps_keeps_them(client, clock):
    item = run_with(client, {"steps": TEMPO})
    r = patch(client, item, targets={"pace_low": 300, "pace_high": 310})
    assert r.status_code == 200, r.text
    assert r.json()["targets"]["steps"] == TEMPO
    assert r.json()["targets"]["pace_low"] == 330


def test_patch_title_keeps_steps(client, clock):
    item = run_with(client, {"steps": TEMPO})
    r = patch(client, item, title="Tempo")
    assert r.json()["title"] == "Tempo"
    assert r.json()["targets"]["steps"] == TEMPO
    assert r.json()["plan_line"] == LINE


def test_steps_null_removes_them(client, clock):
    item = run_with(client, {"steps": TEMPO})
    r = patch(client, item, targets={"steps": None, "distance_m": 8000})
    assert r.status_code == 200, r.text
    got = r.json()
    assert "steps" not in got["targets"]
    assert got["targets"] == {"distance_m": 8000}
    assert got["plan_line"] is None


def test_targets_null_clears_steps(client, clock):
    item = run_with(client, {"steps": TEMPO})
    r = patch(client, item, targets=None)
    assert r.status_code == 200, r.text
    assert r.json()["targets"] is None


def test_sport_change_refused_while_steps(client, clock):
    item = run_with(client, {"steps": TEMPO})
    r = patch(client, item, sport="swim")
    assert r.status_code == 422
    assert "Steps are for runs only" in r.text


def test_old_run_without_steps_unchanged(client, clock):
    old = {"distance_m": 8000, "pace_low": 330, "pace_high": 350}
    item = run_with(client, old)
    assert item["targets"] == old
    assert item["plan_line"] is None
    r = patch(client, item, title="Easy")
    assert r.json()["targets"] == old
