from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from conftest import owner_headers
from focus_helpers import add_session
from sqlalchemy import text

from lockedin.agenda import actual as act
from lockedin.agenda.store import ItemIn, create
from lockedin.app import app
from lockedin.fitness import EstimatedFtp
from lockedin.routes.overview import get_now

NOW = datetime(2026, 10, 29, 20, 0, tzinfo=UTC)
H = owner_headers()
WORKOUT = {"blocks": [{"type": "warmup", "duration_s": 600, "from_power": 0.5, "to_power": 0.75},
                      {"type": "steady", "duration_s": 600, "power": 0.9},
                      {"type": "cooldown", "duration_s": 600, "from_power": 0.65, "to_power": 0.45}]}
PART = [{"label": "Interval 1", "start_s": 600, "end_s": 1200, "from_frac": 0.9, "to_frac": 0.9, "work": True}]


@pytest.fixture
def clock():
    app.dependency_overrides[get_now] = lambda: NOW


def ride(watts: int):
    t = list(range(1800))
    return SimpleNamespace(t_offset=t, power=[watts] * 1800, hr=None, cadence=None)


def test_estimated_ftp_judges_nothing():
    rows, on = act.zwift_parts(PART, ride(170), EstimatedFtp(160))
    assert rows[0]["status"] == "no_target" and rows[0]["avg_w"] == 170 and rows[0]["target_w"] == 144
    assert on is None


def test_owner_ftp_still_judges():
    rows, on = act.zwift_parts(PART, ride(170), 160.0)
    assert rows[0]["status"] == "above" and on is False


def test_session_without_owner_ftp_is_neutral(client, clean_db, clock):
    with clean_db.begin() as c:
        add_session(c, "bike", datetime(2026, 10, 20, 17, tzinfo=UTC), 3600, source="zwift", best_20m_power=180)
        iid = create(c, NOW, ItemIn(day="2026-10-29", sport="bike", title="Tempo", zwift=WORKOUT), "coach")["id"]
        add_session(c, "bike", datetime(2026, 10, 29, 6, tzinfo=UTC), 1800, source="zwift", avg_power=140,
                    power=[110] * 600 + [154] * 600 + [100] * 600)
    d = client.get(f"/api/agenda/{iid}/detail", headers=H).json()
    assert d["plan"]["ftp_is_set"] is False and d["plan"]["ftp"] == 171
    assert [p["status"] for p in d["actual"]["parts"]] == ["no_target"] and d["actual"]["intervals_on_target"] is None
    week = client.get("/api/agenda", params={"week": "2026-10-26"}, headers=H).json()["items"]
    assert "on target" not in week[0]["result"]
    with clean_db.begin() as c:
        c.execute(text("insert into ftp_history (effective_from, ftp) values ('2026-10-01', 171)"))
    assert client.get(f"/api/agenda/{iid}/detail", headers=H).json()["actual"]["intervals_on_target"] is True
