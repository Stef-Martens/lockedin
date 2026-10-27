from datetime import UTC, date, datetime

import pytest
from conftest import ROOT, SYNC_TOKEN, owner_headers
from focus_helpers import add_session
from sqlalchemy import text

from lockedin.agenda.store import ItemIn, create
from lockedin.agenda.zwift_ftp import learn_from_ride
from lockedin.app import app
from lockedin.fit.importer import import_fit
from lockedin.fitness import known_ftp_at, record_zwift_ftp, set_ftp
from lockedin.routes.overview import get_now

NOW = datetime(2026, 10, 29, 20, 0, tzinfo=UTC)
RIDE_AT = datetime(2026, 10, 29, 6, 12, tzinfo=UTC)
SWEET_SPOT = {"blocks": [
    {"type": "warmup", "duration_s": 600, "from_power": 0.5, "to_power": 0.75},
    {"type": "intervals", "repeat": 3, "on_s": 600, "off_s": 300, "on_power": 0.9, "off_power": 0.55},
    {"type": "cooldown", "duration_s": 600, "from_power": 0.65, "to_power": 0.45},
]}
SYNC = {"Authorization": f"Bearer {SYNC_TOKEN}"}


@pytest.fixture
def clock():
    app.dependency_overrides[get_now] = lambda: NOW


def erg_ride(ftp: float, on=(0.9, 0.9, 0.9), seconds=3900) -> list[int]:
    """1 Hz power as ERG holds the Sweet Spot plan: each step at its share of Zwift's FTP, ramps left loose."""
    out = []
    for t in range(seconds):
        if t < 600:
            frac = 0.5 + 0.25 * t / 600
        elif t < 3300:
            k, r = divmod(t - 600, 900)
            frac = on[k] if r < 600 else 0.55
        else:
            frac = 0.65
        out.append(round(frac * ftp))
    return out


def planned_ride(conn, power, day="2026-10-29", start=RIDE_AT) -> int:
    create(conn, NOW, ItemIn(day=day, sport="bike", title="Sweet Spot 3x10", zwift=SWEET_SPOT), "coach")
    return add_session(conn, "bike", start, len(power), source="zwift", power=power, np=150)


def history(conn):
    return [tuple(r) for r in conn.execute(text(
        "select effective_from, ftp, source, activity_id is not null from ftp_history order by effective_from, source"))]


def test_erg_workout_reveals_zwifts_ftp(conn):
    aid = planned_ride(conn, erg_ride(157))
    assert learn_from_ride(conn, aid) == 157
    assert history(conn) == [(date(2026, 10, 29), 157, "zwift", True)]
    assert known_ftp_at(conn, RIDE_AT) == 157
    tss = conn.execute(text("select tss from activities where id = :i"), {"i": aid}).scalar()
    assert tss is not None  # rescored against Zwift's FTP


def test_one_faded_interval_still_reads_the_ftp(conn):
    aid = planned_ride(conn, erg_ride(157, on=(0.9, 0.9, 0.8)))
    assert learn_from_ride(conn, aid) == 157


def test_ride_not_in_erg_teaches_nothing(conn):
    aid = planned_ride(conn, erg_ride(157, on=(1.05, 0.8, 0.95)))
    assert learn_from_ride(conn, aid) is None and history(conn) == []


def test_free_ride_teaches_nothing(conn):
    aid = add_session(conn, "bike", RIDE_AT, 3900, source="zwift", power=erg_ride(157), np=150)
    assert learn_from_ride(conn, aid) is None and history(conn) == []


def test_watch_ride_teaches_nothing(conn):
    create(conn, NOW, ItemIn(day="2026-10-29", sport="bike", title="Sweet Spot 3x10", zwift=SWEET_SPOT), "coach")
    aid = add_session(conn, "bike", RIDE_AT, 3900, power=erg_ride(157), np=150)
    assert learn_from_ride(conn, aid) is None


def test_intervals_are_judged_against_the_learned_ftp(client, clean_db, clock):
    with clean_db.begin() as c:
        aid = planned_ride(c, erg_ride(157, on=(0.9, 0.9, 0.8)))
        learn_from_ride(c, aid)
        item_id = c.execute(text("select id from agenda_items")).scalar()
    d = client.get(f"/api/agenda/{item_id}/detail", headers=owner_headers()).json()
    assert d["plan"]["ftp"] == 157 and d["plan"]["ftp_is_set"] is True
    assert [p["status"] for p in d["actual"]["parts"]] == ["on_target", "on_target", "below"]


def test_earliest_zwift_value_covers_earlier_rides(conn):
    record_zwift_ftp(conn, date(2026, 10, 17), 157)
    record_zwift_ftp(conn, date(2026, 10, 29), 162)
    assert known_ftp_at(conn, datetime(2026, 9, 1, tzinfo=UTC)) == 157
    assert known_ftp_at(conn, datetime(2026, 10, 20, tzinfo=UTC)) == 157
    assert known_ftp_at(conn, datetime(2026, 10, 30, tzinfo=UTC)) == 162


def test_newest_of_owner_and_zwift_wins(conn):
    record_zwift_ftp(conn, date(2026, 10, 17), 157)
    set_ftp(conn, 170, datetime(2026, 10, 20, 12, tzinfo=UTC))
    assert known_ftp_at(conn, datetime(2026, 10, 18, tzinfo=UTC)) == 157
    assert known_ftp_at(conn, datetime(2026, 10, 21, tzinfo=UTC)) == 170
    record_zwift_ftp(conn, date(2026, 10, 25), 160)
    assert known_ftp_at(conn, datetime(2026, 10, 26, tzinfo=UTC)) == 160


def test_clearing_your_ftp_goes_back_to_zwifts(conn):
    record_zwift_ftp(conn, date(2026, 10, 17), 157)
    set_ftp(conn, 170, datetime(2026, 10, 20, 12, tzinfo=UTC))
    set_ftp(conn, None, datetime(2026, 10, 22, 12, tzinfo=UTC))
    assert known_ftp_at(conn, datetime(2026, 10, 23, tzinfo=UTC)) == 157


def test_same_reading_twice_changes_nothing(conn):
    assert record_zwift_ftp(conn, date(2026, 10, 17), 157) is True
    assert record_zwift_ftp(conn, date(2026, 10, 17), 157) is False


def test_log_readings_from_the_mac(client, clean_db, clock):
    r = client.post("/api/fit/zwift-ftp", headers=SYNC, json={"readings": [
        {"at": "2026-10-17T12:38:10Z", "ftp": 157}, {"at": "2026-10-17T12:30:00Z", "ftp": 150}]})
    assert r.status_code == 200 and r.json() == {"recorded": 1}
    profile = client.get("/api/profile", headers=owner_headers()).json()
    assert profile["ftp_now"] == {"w": 157, "source": "zwift", "since": "2026-10-17"}


def test_log_readings_need_the_sync_token(client, clean_db):
    r = client.post("/api/fit/zwift-ftp", json={"readings": [{"at": "2026-10-17T12:38:10Z", "ftp": 157}]})
    assert r.status_code == 401


def test_profile_says_when_ftp_is_only_estimated(client, clean_db, clock):
    with clean_db.begin() as c:
        add_session(c, "bike", datetime(2026, 10, 1, tzinfo=UTC), 3600, source="zwift", best_20m_power=200)
    assert client.get("/api/profile", headers=owner_headers()).json()["ftp_now"] == {"w": 190, "source": "estimate", "since": None}


def test_importing_the_workout_ride_learns_zwifts_ftp(conn, tmp_path):
    import sys
    sys.path.insert(0, str(ROOT / "scripts"))
    from fit_tool.profile.profile_type import Manufacturer, Sport, SubSport
    from make_samples import build

    power = erg_ride(157)
    recs = [{"t": t, "power": w, "cadence": 88, "speed": 8.0, "distance": 8.0 * t} for t, w in enumerate(power)]
    path = tmp_path / "erg.fit"
    build(str(path), manufacturer=Manufacturer.ZWIFT.value, sport=Sport.CYCLING, sub_sport=SubSport.VIRTUAL_ACTIVITY,
          start=RIDE_AT, duration_s=len(power), records=recs, session={"total_distance": 8.0 * len(power)})
    create(conn, NOW, ItemIn(day="2026-10-29", sport="bike", title="Sweet Spot 3x10", zwift=SWEET_SPOT), "coach")
    r = import_fit(conn, path.read_bytes(), "erg.fit", None)
    assert r.status == "imported" and history(conn) == [(date(2026, 10, 29), 157, "zwift", True)]


RECOVERY_SPIN = {"blocks": [
    {"type": "warmup", "duration_s": 300, "from_power": 0.4, "to_power": 0.58},
    {"type": "steady", "duration_s": 1200, "power": 0.6},
    {"type": "cooldown", "duration_s": 300, "from_power": 0.55, "to_power": 0.4},
]}


def spin(conn, watts_at) -> int:
    create(conn, NOW, ItemIn(day="2026-10-29", sport="bike", title="Recovery Spin 30", zwift=RECOVERY_SPIN), "coach")
    return add_session(conn, "bike", RIDE_AT, 1800, source="zwift", power=[watts_at(t) for t in range(1800)], np=100)


def test_one_steady_block_in_erg_is_enough(conn):
    # As ridden on 26 Oct: ERG at 100 W for 60%, held within a watt or two, one short surge.
    aid = spin(conn, lambda t: 100 + (t % 3) - 1 + (40 if 700 <= t < 720 else 0))
    assert learn_from_ride(conn, aid) == 167  # 100 W is 60% of 166 or 167: Zwift rounds its targets


def test_one_steady_block_ridden_freely_teaches_nothing(conn):
    aid = spin(conn, lambda t: 100 + 25 * ((t // 60) % 3 - 1))  # minute by minute 75, 100, 125 W
    assert learn_from_ride(conn, aid) is None


def test_the_macs_regular_call_catches_up_on_recent_workout_rides(client, clean_db, clock):
    with clean_db.begin() as c:
        planned_ride(c, erg_ride(166))  # already stored, never learned from
        old = planned_ride(c, erg_ride(150), day="2026-10-01", start=datetime(2026, 10, 1, 6, tzinfo=UTC))
    assert client.post("/api/agenda/zwift/sync", headers=SYNC).status_code == 200
    with clean_db.begin() as c:
        assert history(c) == [(date(2026, 10, 29), 166, "zwift", True)]  # the 1 Oct ride is too old to revisit
        assert old not in c.execute(text("select activity_id from ftp_history")).scalars().all()
