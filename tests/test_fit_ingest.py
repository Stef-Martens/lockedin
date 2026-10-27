from datetime import UTC, datetime

import pytest
from conftest import SYNC_HEADERS, count, get_activity, read, stream
from sqlalchemy import text

from lockedin.fit.importer import import_fit, known_hashes
from lockedin.fit.parse import parse_fit, parse_fit_activities


def test_a_multisport_file_is_one_activity_per_sport_without_the_transition():
    bike, run = parse_fit_activities(read("watch_brick.fit"))
    assert (bike.sport, bike.sub_type, bike.duration_s) == ("bike", "cycling/road", 3600)
    assert bike.start_at == datetime(2026, 10, 25, 8, 0, tzinfo=UTC) and bike.avg_power == 200
    assert len(bike.streams.t_offset) == 3600 and bike.streams.t_offset[-1] == 3599
    assert (run.sport, run.sub_type, run.duration_s) == ("run", "running/street", 1500)
    assert run.start_at == datetime(2026, 10, 25, 9, 0, 30, tzinfo=UTC)
    assert run.distance_m == pytest.approx(5000) and run.avg_hr == 160
    assert len(run.streams.t_offset) == 1500 and run.streams.t_offset[0] == 0
    assert parse_fit(read("watch_brick.fit")).sport == "bike"


def test_a_multisport_file_imports_each_leg(conn):
    r = import_fit(conn, read("watch_brick.fit"), "brick.fit", None)
    assert r.status == "imported"
    rows = conn.execute(text("select id, sport, source_ref, avg_pace_s_per_km from activities order by start_at")).all()
    assert [x.sport for x in rows] == ["bike", "run"] and r.activity_id == rows[0].id
    assert rows[0].source_ref == r.sha256 and rows[1].source_ref != r.sha256
    assert rows[1].avg_pace_s_per_km == pytest.approx(300)
    assert len(stream(conn, rows[1].id).t_offset) == 1500
    assert known_hashes(conn, [r.sha256]) == {r.sha256}
    again = import_fit(conn, read("watch_brick.fit"), "brick.fit", None)
    assert again.status == "duplicate" and count(conn, "activities") == 2


def test_pool_swim_pace_leaves_out_rest_at_the_wall():
    f = parse_fit(read("watch_pool_swim_rest.fit"))
    assert (f.swim_lengths, f.duration_s, f.swim_active_s) == (40, 1920, 1800)


def test_pool_swim_pace_from_active_lengths(conn):
    row = get_activity(conn, import_fit(conn, read("watch_pool_swim_rest.fit"), "s.fit", None).activity_id)
    assert row.swim_pace_s_per_100m == pytest.approx(180)  # 40 × 45 s over 1000 m, not the 32 min with rest


def test_open_water_swim_pace_from_gps_distance(conn):
    row = get_activity(conn, import_fit(conn, read("watch_open_water.fit"), "ow.fit", None).activity_id)
    assert (row.sport, row.sub_type, row.pool_length_m) == ("swim", "swimming/open_water", None)
    assert row.distance_m == pytest.approx(1500) and row.swim_pace_s_per_100m == pytest.approx(120)


def test_a_known_unreadable_file_is_answered_without_reparsing(conn, monkeypatch):
    first = import_fit(conn, read("corrupt.fit"), "c.fit", "zwift")
    assert first.status == "error" and first.already_failed is False

    import lockedin.fit.importer as imp

    def no_parse(data):
        raise AssertionError("parsed again")

    monkeypatch.setattr(imp, "parse_fit_activities", no_parse)
    again = import_fit(conn, read("corrupt.fit"), "c.fit", "zwift")
    assert (again.status, again.error, again.already_failed) == ("error", first.error, True)
    assert known_hashes(conn, [first.sha256]) == set()


def test_a_processing_error_is_retried(conn, monkeypatch):
    import lockedin.fit.importer as imp
    real = imp.normalized_power
    monkeypatch.setattr(imp, "normalized_power", lambda *a: 1 / 0)
    assert import_fit(conn, read("zwift_ride.fit"), "z.fit", "zwift").status == "error"
    monkeypatch.setattr(imp, "normalized_power", real)
    r = import_fit(conn, read("zwift_ride.fit"), "z.fit", "zwift")
    assert r.status == "imported" and r.already_failed is False


def test_fit_route_reports_already_failed_in_the_same_shape(client):
    def up():
        return client.post("/api/fit/upload", files={"file": ("c.fit", read("corrupt.fit"))}, headers=SYNC_HEADERS)
    first, again = up().json(), up().json()
    assert set(first) <= set(again) and again["status"] == "error" and again["error"] == first["error"]
    assert first["already_failed"] is False and again["already_failed"] is True


def test_fit_upload_too_large_is_rejected_on_the_bytes(client, monkeypatch):
    import dataclasses

    import lockedin.routes.fit as route
    small = dataclasses.replace(route.get_settings(), max_upload_bytes=100)
    monkeypatch.setattr(route, "get_settings", lambda: small)
    r = client.post("/api/fit/upload", files={"file": ("z.fit", read("zwift_ride.fit"))}, headers=SYNC_HEADERS)
    assert r.status_code == 413
