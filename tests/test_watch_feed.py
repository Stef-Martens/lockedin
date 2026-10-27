"""The watch feed: the coming week's runs and swims, as the iPhone app decodes them."""

import json
import os
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from conftest import SYNC_HEADERS, WATCH_HEADERS, owner_headers
from fastapi import HTTPException
from focus_helpers import add_session
from sqlalchemy import text
from test_run_steps import TEMPO

from lockedin import auth, timeoff
from lockedin.app import app
from lockedin.config import get_settings
from lockedin.routes.overview import get_now
from lockedin.timeoff import Restriction, TimeOffIn

H = owner_headers()
NOW = datetime(2026, 10, 27, 8, 0, tzinfo=UTC)  # Tuesday
SAMPLE = Path(__file__).resolve().parent.parent / "ios" / "Tests" / "feed-sample.json"
SWIM = {"distance_m": 1500, "pace_low": 120, "pace_high": 120}


@pytest.fixture
def clock():
    app.dependency_overrides[get_now] = lambda: NOW


@pytest.fixture
def max_hr(clean_db):
    with clean_db.begin() as c:
        c.execute(text("update profile set max_hr_override = 190"))


def add(client, day: str, sport: str, title: str, **body) -> dict:
    r = client.post("/api/agenda", headers=H, json={"day": day, "sport": sport, "title": title, **body})
    assert r.status_code == 201, r.text
    return r.json()


def feed(client, headers=WATCH_HEADERS) -> dict:
    r = client.get("/api/watch/runs", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def one_step(target: dict) -> dict:
    return {"steps": {"blocks": [{"repeat": 1, "steps": [{"kind": "work", "goal": {"time_s": 600}, "target": target}]}]}}


def numbered(body: dict) -> dict:
    """Item ids as 1, 2, … so the sample stays the same from run to run."""
    return {**body, "items": [{**i, "id": n} for n, i in enumerate(body["items"], 1)]}


def test_feed_contract(client, clock, max_hr):
    add(client, "2026-10-27", "run", "Tempo", targets={"steps": TEMPO})
    add(client, "2026-10-28", "swim", "Swim", note="4 × 100 m, 30 s rest", targets=SWIM)
    got = numbered(feed(client))
    if os.environ.get("UPDATE_FEED_SAMPLE") == "1":
        SAMPLE.parent.mkdir(parents=True, exist_ok=True)
        SAMPLE.write_text(json.dumps(got, indent=2, ensure_ascii=False) + "\n")
    assert got == json.loads(SAMPLE.read_text())
    run = got["items"][0]
    assert run["summary"] == "10' warm-up Z2 · 4 × (5' @ 5:30–5:50, 2' jog) · cool-down"
    assert run["workout"]["warmup"]["alert"] == {"type": "heart_rate", "min_bpm": 137, "max_bpm": 156}
    assert run["workout"]["blocks"][0]["steps"][0]["alert"] == {"type": "speed", "min_mps": 2.857, "max_mps": 3.03}
    assert run["workout"]["blocks"][0]["iterations"] == 4


def test_zone_one_starts_at_60_percent(client, clock, max_hr):
    add(client, "2026-10-28", "run", "Easy", targets=one_step({"hr_zone": 1}))
    alert = feed(client)["items"][0]["workout"]["blocks"][0]["steps"][0]["alert"]
    assert alert == {"type": "heart_rate", "min_bpm": round(190 * 0.60), "max_bpm": round(190 * 0.72)}


def test_no_max_hr_drops_hr_alert(client, clock):
    add(client, "2026-10-28", "run", "Easy", targets=one_step({"hr_zone": 2}))
    assert feed(client)["items"][0]["workout"]["blocks"][0]["steps"][0]["alert"] is None


def test_window_and_filters(client, clean_db, clock):
    add(client, "2026-10-26", "run", "Yesterday")
    add(client, "2026-11-04", "run", "Eight days ahead")
    add(client, "2026-10-27", "run", "Done")
    add(client, "2026-10-30", "run", "Time off")
    add(client, "2026-10-28", "gym", "Gym")
    add(client, "2026-10-28", "bike", "Ride")
    add(client, "2026-11-03", "run", "Last day")
    add(client, "2026-10-29", "swim", "Swim")
    add(client, "2026-10-28", "run", "Optional", optional=True)
    with clean_db.begin() as c:
        add_session(c, "run", datetime(2026, 10, 27, 6, tzinfo=UTC), 2400)
        timeoff.create(c, TimeOffIn(reason="injury", start=date(2026, 10, 30),
                                    restrictions=[Restriction(category="run", until=date(2026, 10, 30))]))
    items = feed(client)["items"]
    assert [i["title"] for i in items] == ["Optional", "Swim", "Last day"]
    assert items[0]["optional"] is True and items[1]["optional"] is False


def test_run_without_steps(client, clock):
    add(client, "2026-10-28", "run", "Steady", targets={"distance_m": 8000, "pace_low": 330, "pace_high": 350})
    item = feed(client)["items"][0]
    assert item["summary"] == "8 km @ 5:30–5:50"
    assert item["workout"] == {
        "kind": "run", "display_name": "Steady", "location": "outdoor", "warmup": None,
        "blocks": [{"iterations": 1, "steps": [{"purpose": "work", "goal": {"type": "distance", "meters": 8000},
                                                 "alert": {"type": "speed", "min_mps": 2.857, "max_mps": 3.03}}]}],
        "cooldown": None}


def test_run_and_swim_goals_fall_back(client, clock):
    add(client, "2026-10-28", "run", "Long", targets={"duration_s": 3600})
    add(client, "2026-10-29", "run", "Free")
    add(client, "2026-10-30", "swim", "Swim")
    run, free, swim = feed(client)["items"]
    assert run["workout"]["blocks"][0]["steps"][0] == {"purpose": "work", "goal": {"type": "time", "seconds": 3600},
                                                        "alert": None}
    assert free["workout"]["blocks"][0]["steps"][0]["goal"] == {"type": "open"}
    assert free["summary"] is None
    assert swim["workout"] == {"kind": "swim", "display_name": "Swim", "location": "pool", "goal": {"type": "open"}}


def test_auth(client, clock):
    assert client.get("/api/watch/runs", headers=H).status_code == 200
    assert client.get("/api/watch/runs", headers=WATCH_HEADERS).status_code == 200
    assert client.get("/api/watch/runs").status_code == 401
    assert client.get("/api/watch/runs", headers=SYNC_HEADERS).status_code == 401
    assert client.get("/api/agenda", headers=WATCH_HEADERS).status_code == 401


@pytest.mark.parametrize("watch_token", ["", "short"])
def test_short_or_empty_watch_token_never_authenticates(client, monkeypatch, watch_token):
    s = replace(get_settings(), watch_token=watch_token)
    monkeypatch.setattr(auth, "get_settings", lambda: s)
    for header in ("Bearer ", "Bearer short"):
        assert client.get("/api/watch/runs", headers={"Authorization": header}).status_code == 401
        with pytest.raises(HTTPException) as e:
            auth.require_owner_or_watch(header)
        assert e.value.status_code == 401
