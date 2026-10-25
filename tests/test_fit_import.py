import pytest
from conftest import count, get_activity, read
from sqlalchemy import text

from lockedin.fit.importer import import_fit, known_hashes


def test_import_then_duplicate(conn):
    r1 = import_fit(conn, read("zwift_ride.fit"), "a.fit", "zwift")
    assert r1.status == "imported" and r1.activity_id
    r2 = import_fit(conn, read("zwift_ride.fit"), "renamed.fit", None)
    assert r2.status == "duplicate" and r2.activity_id == r1.activity_id
    assert count(conn, "activities") == 1
    assert known_hashes(conn, [r1.sha256, "nope"]) == {r1.sha256}


def test_corrupt_is_error_and_retryable(conn):
    r = import_fit(conn, read("corrupt.fit"), "c.fit", "zwift")
    assert r.status == "error" and r.error and r.activity_id is None
    assert known_hashes(conn, [r.sha256]) == set()
    assert import_fit(conn, read("corrupt.fit"), "c.fit", "zwift").status == "error"
    assert count(conn, "fit_files") == 1


def test_source_detected_from_manufacturer(conn):
    a = import_fit(conn, read("zwift_ride.fit"), "x.fit", None)
    b = import_fit(conn, read("watch_run.fit"), "y.fit", None)
    assert get_activity(conn, a.activity_id).source == "zwift"
    assert get_activity(conn, b.activity_id).source == "healthfit"


def test_summary_and_streams_stored(conn):
    a = import_fit(conn, read("zwift_ride.fit"), "x.fit", "zwift")
    row = get_activity(conn, a.activity_id)
    assert (row.sport, row.sub_type, row.duration_s, row.avg_power, row.max_power) == ("bike", "cycling/virtual_activity", 3600, 200, 250)
    assert row.best_20m_power == pytest.approx(250)
    s = conn.execute(text("select array_length(power, 1), array_length(t_offset, 1) from activity_streams where activity_id = :i"),
                     {"i": a.activity_id}).one()
    assert tuple(s) == (3600, 3600)


def test_tss_with_override(conn):
    conn.execute(text("update profile set ftp_override = 250"))
    row = get_activity(conn, import_fit(conn, read("zwift_ride.fit"), "x.fit", "zwift").activity_id)
    # NP of 30 min @150 W + 30 min @250 W ≈ 217; IF = 217/250; TSS = IF² × 100 for 1 h
    assert row.np == pytest.approx(217, abs=3)
    assert row.if_ == pytest.approx(0.867, abs=0.015)
    assert row.tss == pytest.approx(75.2, abs=2.5)


def test_first_ride_does_not_set_its_own_ftp(conn):
    row = get_activity(conn, import_fit(conn, read("zwift_ride.fit"), "x.fit", "zwift").activity_id)
    assert row.np == pytest.approx(217, abs=3)
    assert row.if_ is None and row.tss is None  # no earlier rides and no FTP set


def test_tss_from_earlier_rides(conn):
    import_fit(conn, read("zwift_ride_earlier.fit"), "e.fit", "zwift")
    row = get_activity(conn, import_fit(conn, read("zwift_ride.fit"), "x.fit", "zwift").activity_id)
    # FTP = 0.95 × the earlier ride's best 20 min (250 W) = 237.5 W
    assert row.if_ == pytest.approx(217 / 237.5, abs=0.015)


def test_backfilling_an_earlier_ride_updates_later_ones(conn):
    later = import_fit(conn, read("zwift_ride.fit"), "x.fit", "zwift").activity_id
    assert get_activity(conn, later).tss is None
    import_fit(conn, read("zwift_ride_earlier.fit"), "e.fit", "zwift")
    assert get_activity(conn, later).if_ == pytest.approx(217 / 237.5, abs=0.015)


def test_run_pace(conn):
    row = get_activity(conn, import_fit(conn, read("watch_run.fit"), "r.fit", "healthfit").activity_id)
    assert row.avg_pace_s_per_km == pytest.approx(337.5, abs=1)


def test_swim_pace_and_lengths(conn):
    row = get_activity(conn, import_fit(conn, read("watch_pool_swim.fit"), "s.fit", "healthfit").activity_id)
    assert (row.sport, row.pool_length_m, row.swim_lengths, row.swim_strokes) == ("swim", 25.0, 40, 720)
    assert row.swim_pace_s_per_100m == pytest.approx(180, abs=1)


def test_import_logged(conn):
    import_fit(conn, read("watch_run.fit"), "r.fit", None)
    assert conn.execute(text("select source from import_log")).scalars().all() == ["healthfit"]


def test_reexport_with_different_bytes_is_a_duplicate(conn):
    first = import_fit(conn, read("watch_run.fit"), "a.fit", None)
    again = import_fit(conn, read("watch_run_reexport.fit"), "b.fit", None)
    assert again.status == "duplicate" and again.activity_id == first.activity_id
    assert again.sha256 != first.sha256
    assert count(conn, "activities") == 1
    assert known_hashes(conn, [again.sha256]) == {again.sha256}  # the sync script won't resend it


def test_unexpected_processing_error_is_reported_not_raised(conn, monkeypatch):
    import lockedin.fit.importer as imp

    def boom(*a, **k):
        raise IndexError("weird file")

    monkeypatch.setattr(imp, "normalized_power", boom)
    r = import_fit(conn, read("zwift_ride.fit"), "z.fit", "zwift")
    assert r.status == "error" and "weird file" in r.error
    assert count(conn, "activities") == 0 and count(conn, "activity_streams") == 0
    assert known_hashes(conn, [r.sha256]) == set()
