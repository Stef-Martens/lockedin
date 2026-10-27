from datetime import UTC, date, datetime, timedelta

import pytest
from conftest import owner_headers
from focus_helpers import add_gym, add_session
from sqlalchemy import text

from lockedin.app import app
from lockedin.focus.load import activity_loads, hr_tss, pmc
from lockedin.routes.overview import get_now

NOW = datetime(2026, 10, 27, 20, 0, tzinfo=UTC)
TODAY = date(2026, 10, 27)
H = owner_headers()


@pytest.fixture
def clock():
    app.dependency_overrides[get_now] = lambda: NOW


def loads(conn, days=30):
    return activity_loads(conn, NOW - timedelta(days=days), NOW)


def test_an_hour_at_threshold_hr_is_100():
    assert hr_tss([178] * 3600, list(range(3600)), None, 3600, max_hr=200, resting_hr=60, sex=None) == pytest.approx(100)


def test_easy_hour_scores_well_under_threshold():
    easy = hr_tss([140] * 3600, list(range(3600)), None, 3600, max_hr=200, resting_hr=60, sex="male")
    assert 35 < easy < 55


def test_sparse_samples_scale_to_moving_time():
    swim = hr_tss([178] * 40, list(range(0, 1800, 45)), None, 1800, max_hr=200, resting_hr=60, sex=None)
    assert swim == pytest.approx(50, abs=0.5)


def test_average_hr_when_there_is_no_stream():
    assert hr_tss(None, None, 178, 1800, max_hr=200, resting_hr=60, sex="female") == pytest.approx(50)


def test_each_sport_gets_its_load(conn):
    conn.execute(text("update profile set max_hr_override = 200"))
    ride = add_session(conn, "bike", NOW - timedelta(days=1), 3600, source="zwift", hr=[178] * 3600)
    conn.execute(text("update activities set tss = 72.5 where id = :i"), {"i": ride})
    add_session(conn, "bike", NOW - timedelta(days=2), 3600, hr=[178] * 3600)          # no power: by HR
    add_session(conn, "run", NOW - timedelta(days=3), 1800, hr=[178] * 1800)
    add_session(conn, "swim", NOW - timedelta(days=4), 1800, avg_hr=178)
    add_gym(conn, NOW - timedelta(days=5), [("Squat", 100, 5, "normal")], duration_s=5400)
    add_session(conn, "other", NOW - timedelta(days=6), 3600, sub_type="walking/generic", avg_hr=178)  # not counted
    dup = add_session(conn, "run", NOW - timedelta(days=7), 1800, avg_hr=178)
    add_session(conn, "run", NOW - timedelta(days=7), 1800, avg_hr=178, superseded_by=dup)
    got = {d: round(v, 1) for d, v in loads(conn).items()}
    assert got == {date(2026, 10, 26): 72.5, date(2026, 10, 25): 100.0, date(2026, 10, 24): 50.0,
                   date(2026, 10, 23): 50.0, date(2026, 10, 22): 60.0, date(2026, 10, 20): 50.0}


def test_no_hr_and_no_power_assumes_a_moderate_session(conn):
    add_session(conn, "run", NOW - timedelta(days=1), 3600)
    add_session(conn, "other", NOW - timedelta(days=2), 3600, sub_type="yoga")
    assert loads(conn) == {date(2026, 10, 26): pytest.approx(49)}


def test_a_late_session_counts_on_its_brussels_day(conn):
    add_session(conn, "run", datetime(2026, 10, 20, 23, 30, tzinfo=UTC), 3600)  # 00:30 on the 21st
    assert list(loads(conn)) == [date(2026, 10, 21)]


def test_pmc_exponential_averages():
    rows = pmc({date(2026, 10, 1): 100.0}, date(2026, 10, 1), date(2026, 10, 3))
    assert [r["day"] for r in rows] == [date(2026, 10, 1), date(2026, 10, 2), date(2026, 10, 3)]
    assert rows[0]["fitness"] == pytest.approx(100 / 42) and rows[0]["fatigue"] == pytest.approx(100 / 7)
    assert rows[0]["form"] == 0  # yesterday's fitness − fatigue
    assert rows[1]["load"] == 0 and rows[1]["form"] == pytest.approx(100 / 42 - 100 / 7)
    assert rows[2]["fatigue"] == pytest.approx(100 / 7 * (6 / 7) ** 2)


def test_endpoint_contract(client, clean_db, clock):
    with clean_db.begin() as c:
        add_session(c, "run", NOW - timedelta(days=200), 3600)  # before the window: seeds fitness
        add_session(c, "run", NOW - timedelta(hours=2), 3600)
    r = client.get("/api/load", headers=H)
    assert r.status_code == 200
    body = r.json()
    days = body["days"]
    assert len(days) == 180 and days[-1]["day"] == "2026-10-27" and days[0]["day"] == "2026-05-01"
    assert set(days[0]) == {"day", "load", "fitness", "fatigue", "form"}
    assert days[0]["fitness"] > 0 and days[0]["load"] == 0
    assert days[-1]["load"] == 49.0
    assert body["today"] == {k: days[-1][k] for k in ("fitness", "fatigue", "form")}
    assert all(isinstance(v, float) and round(v, 1) == v for d in days for k, v in d.items() if k != "day")


def test_endpoint_days_param_is_clamped(client, clean_db, clock):
    assert len(client.get("/api/load", params={"days": 10}, headers=H).json()["days"]) == 30
    assert len(client.get("/api/load", params={"days": 9999}, headers=H).json()["days"]) == 365
    assert len(client.get("/api/load", params={"days": 90}, headers=H).json()["days"]) == 90


def test_no_activities_at_all(client, clean_db, clock):
    body = client.get("/api/load", headers=H).json()
    assert body["today"] is None and len(body["days"]) == 180 and all(d["load"] == 0 for d in body["days"])


def test_owner_only(client):
    assert client.get("/api/load").status_code == 401
