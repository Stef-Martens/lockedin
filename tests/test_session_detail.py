from datetime import UTC, datetime

import pytest
from conftest import owner_headers
from focus_helpers import add_gym, add_session
from sqlalchemy import text

from lockedin.agenda.store import ItemIn, create
from lockedin.app import app
from lockedin.routes.overview import get_now

NOW = datetime(2026, 10, 29, 20, 0, tzinfo=UTC)  # Thursday evening
H = owner_headers()
SWEET_SPOT = {"blocks": [
    {"type": "warmup", "duration_s": 600, "from_power": 0.5, "to_power": 0.75},
    {"type": "intervals", "repeat": 3, "on_s": 600, "off_s": 300, "on_power": 0.9, "off_power": 0.55},
    {"type": "cooldown", "duration_s": 600, "from_power": 0.65, "to_power": 0.45},
]}
BENCH, OHP = "Bench Press (Barbell)", "Overhead Press (Dumbbell)"


@pytest.fixture
def clock():
    app.dependency_overrides[get_now] = lambda: NOW


def add(conn, **fields):
    return create(conn, NOW, ItemIn(**fields), "coach")["id"]


def detail(client, item_id):
    r = client.get(f"/api/agenda/{item_id}/detail", headers=H)
    assert r.status_code == 200, r.text
    return r.json()


def ride_power(on_watts, seconds=3900):
    """1 Hz power: plan-shaped ride with the three intervals at the given watts."""
    out = []
    for t in range(seconds):
        if 600 <= t < 1200:
            w = on_watts[0]
        elif 1500 <= t < 2100:
            w = on_watts[1]
        elif 2400 <= t < 3000:
            w = on_watts[2]
        else:
            w = 95
        out.append(w)
    return out


def test_zwift_plan_breakdown(client, clean_db, clock):
    with clean_db.begin() as c:
        c.execute(text("update profile set ftp_override = 168"))
        iid = add(c, day="2026-10-30", sport="bike", title="Sweet Spot 3x10", zwift=SWEET_SPOT)
    d = detail(client, iid)
    plan = d["plan"]
    assert plan["kind"] == "zwift" and plan["ftp"] == 168 and d["actual"] is None
    # Zwift's IntervalsT ends with a recovery after the last interval too.
    assert [p["label"] for p in plan["parts"]] == ["Warm-up", "Interval 1", "Recovery", "Interval 2", "Recovery",
                                                    "Interval 3", "Recovery", "Cool-down"]
    assert plan["parts"][1] == {"label": "Interval 1", "start_s": 600, "end_s": 1200, "from_w": 151, "to_w": 151,
                                "from_frac": 0.9, "to_frac": 0.9, "work": True}
    assert plan["sweet_spot_min"] == 30 and plan["tss_est"] == pytest.approx(58, abs=2)


def test_zwift_done_on_target(client, clean_db, clock):
    with clean_db.begin() as c:
        c.execute(text("update profile set ftp_override = 168"))
        iid = add(c, day="2026-10-29", sport="bike", title="Sweet Spot 3x10", zwift=SWEET_SPOT)
        add_session(c, "bike", datetime(2026, 10, 29, 6, 12, tzinfo=UTC), 3900, source="zwift", avg_power=128,
                    power=ride_power((151, 149, 153)), hr=[140] * 3900)
    d = detail(client, iid)
    a = d["actual"]
    assert [p["status"] for p in a["parts"]] == ["on_target"] * 3
    assert [p["avg_w"] for p in a["parts"]] == [151, 149, 153] and a["intervals_on_target"] is True
    assert len(a["power"]) <= 600 and a["avg_power"] == 128
    week = client.get("/api/agenda", params={"week": "2026-10-26"}, headers=H).json()["items"]
    assert week[0]["result"] == "Done · 65′ · 128 W · intervals on target"


def test_zwift_stopped_early(client, clean_db, clock):
    with clean_db.begin() as c:
        c.execute(text("update profile set ftp_override = 168"))
        iid = add(c, day="2026-10-29", sport="bike", title="Sweet Spot 3x10", zwift=SWEET_SPOT)
        add_session(c, "bike", datetime(2026, 10, 29, 6, 12, tzinfo=UTC), 1320, source="zwift",
                    power=ride_power((151, 149, 153), 1320))
    parts = detail(client, iid)["actual"]["parts"]
    assert parts[0]["status"] == "on_target" and parts[1]["status"] is None and parts[1]["avg_w"] is None
    assert detail(client, iid)["actual"]["intervals_on_target"] is None


def test_detail_uses_the_ride_that_ticked_it(client, clean_db, clock):
    with clean_db.begin() as c:
        iid = add(c, day="2026-10-29", sport="bike", title="Ride", zwift=SWEET_SPOT)
        first = add_session(c, "bike", datetime(2026, 10, 29, 6, tzinfo=UTC), 3600, source="zwift")
        add_session(c, "bike", datetime(2026, 10, 29, 17, tzinfo=UTC), 1800, source="zwift")
    assert detail(client, iid)["actual"]["activity_id"] == first


def _run_streams(conn, aid, km=8.2, pace=342):
    n = int(km * pace)
    conn.execute(text(
        "insert into activity_streams (activity_id, t_offset, hr, speed, distance) values "
        "(:i, cast(:t as integer[]), cast(:h as smallint[]), cast(:s as real[]), cast(:d as real[]))"
    ), {"i": aid, "t": list(range(n)), "h": [150] * n, "s": [1000 / pace] * n, "d": [t * 1000 / pace for t in range(n)]})


def test_run_plan_and_done(client, clean_db, clock):
    with clean_db.begin() as c:
        c.execute(text("update profile set max_hr_override = 190"))
        iid = add(c, day="2026-10-29", sport="run", title="Steady run",
                  targets={"duration_s": 2400, "pace_low": 335, "pace_high": 350, "hr_zone": 2})
        aid = add_session(c, "run", datetime(2026, 10, 29, 7, tzinfo=UTC), 2872, distance_m=8400, avg_hr=150, avg_pace=342)
        _run_streams(c, aid, km=8.4)  # 8 full km plus a ~0.4 km last split
    d = detail(client, iid)
    assert d["plan"]["kind"] == "targets" and d["plan"]["hr_bpm"] is not None
    a = d["actual"]
    assert [s["km"] for s in a["splits"]][:8] == list(range(1, 9)) and len(a["splits"]) == 9
    assert a["splits"][0]["status"] == "on_target"
    assert a["splits"][-1]["km"] == pytest.approx(8.4, abs=0.05)
    assert sum(a["zones"].values()) == pytest.approx(2872, abs=5)


def test_run_without_streams(client, clean_db, clock):
    with clean_db.begin() as c:
        iid = add(c, day="2026-10-29", sport="run", title="Run")
        add_session(c, "run", datetime(2026, 10, 29, 7, tzinfo=UTC), 1800, distance_m=5000, avg_pace=360)
    a = detail(client, iid)["actual"]
    assert a["splits"] is None and a["zones"] is None and a["distance_m"] == 5000
    week = client.get("/api/agenda", params={"week": "2026-10-26"}, headers=H).json()["items"]
    assert week[0]["result"] == "Done · 5.0 km · 6:00/km"


def test_swim_done(client, clean_db, clock):
    with clean_db.begin() as c:
        iid = add(c, day="2026-10-29", sport="swim", title="Pool", targets={"distance_m": 1500, "pace_low": 120, "pace_high": 130})
        add_session(c, "swim", datetime(2026, 10, 29, 7, tzinfo=UTC), 1900, distance_m=1500, swim_pace=126.7)
    a = detail(client, iid)["actual"]
    assert a["distance_m"] == 1500 and a["swim_pace_s_per_100m"] == pytest.approx(126.7)
    week = client.get("/api/agenda", params={"week": "2026-10-26"}, headers=H).json()["items"]
    assert week[0]["result"] == "Done · 1500 m · 2:07/100 m"


def test_gym_done_against_the_saved_plan(client, clean_db, clock):
    with clean_db.begin() as c:
        add_gym(c, datetime(2026, 10, 24, 17, tzinfo=UTC), [(BENCH, 80, 8, "normal")] * 3 + [(OHP, 40, 10, "normal")] * 3,
                title="Push")
        iid = add(c, day="2026-10-29", sport="gym", title="Push", routine="Push")
    plan = client.get("/api/plan", params={"day": "Push"}, headers=H).json()
    extra = next(i for i in plan["items"] if i["kind"] == "add")
    client.post(f"/api/plan/{plan['id']}/items/{extra['id']}/skip", headers=H)
    with clean_db.begin() as c:
        add_gym(c, datetime(2026, 10, 29, 17, tzinfo=UTC),
                [(BENCH, 80, 8, "normal")] * 3 + [(OHP, 40, 7, "normal")] * 3 + [("Triceps Pushdown", 30, 10, "normal")] * 2,
                title="Push")
    rows = {r["exercise"]: r for r in detail(client, iid)["actual"]["rows"]}
    assert rows[BENCH]["status"] == "done" and rows[OHP]["status"] == "close"
    assert rows[extra["exercise"]]["status"] == "skipped_by_you" and rows[extra["exercise"]]["extra"] is True
    assert rows["Triceps Pushdown"]["status"] == "added"
    week = client.get("/api/agenda", params={"week": "2026-10-26"}, headers=H).json()["items"]
    assert week[0]["result"] == "Done · 3 exercises · 60′"


def test_gym_done_without_a_saved_plan(client, clean_db, clock):
    with clean_db.begin() as c:
        add_gym(c, datetime(2026, 10, 24, 17, tzinfo=UTC), [(BENCH, 80, 8, "normal")] * 3, title="Push")
        iid = add(c, day="2026-10-29", sport="gym", title="Push", routine="Push")
        add_gym(c, datetime(2026, 10, 29, 17, tzinfo=UTC), [(BENCH, 80, 9, "normal")] * 3, title="Push")
    rows = detail(client, iid)["actual"]["rows"]
    assert [(r["exercise"], r["status"]) for r in rows] == [(BENCH, "done")]
    assert rows[0]["planned"]["weight_kg"] == 80  # the target before this session, not after it


def test_detail_errors(client, clock):
    assert client.get("/api/agenda/999/detail", headers=H).status_code == 404
    assert client.get("/api/agenda/1/detail").status_code == 401


def test_no_ftp_means_no_target_not_not_ridden(client, clean_db, clock):
    with clean_db.begin() as c:
        iid = add(c, day="2026-10-29", sport="bike", title="Sweet Spot 3x10", zwift=SWEET_SPOT)
        add_session(c, "bike", datetime(2026, 10, 29, 6, 12, tzinfo=UTC), 3900, source="zwift", power=ride_power((151, 149, 153)))
    parts = detail(client, iid)["actual"]["parts"]
    assert [p["status"] for p in parts] == ["no_target"] * 3 and parts[0]["avg_w"] == 151


def test_result_lines_only_when_asked(clean_db):
    from lockedin.agenda.store import items_between
    with clean_db.begin() as c:
        add(c, day="2026-10-29", sport="bike", title="Ride")
        add_session(c, "bike", datetime(2026, 10, 29, 6, tzinfo=UTC), 3600, source="zwift", avg_power=150)
        assert items_between(c, NOW, datetime(2026, 10, 29).date(), datetime(2026, 10, 29).date())[0]["result"] is None
        lines = items_between(c, NOW, datetime(2026, 10, 29).date(), datetime(2026, 10, 29).date(), results=True)
        assert lines[0]["result"] == "Done · 60′ · 150 W"
