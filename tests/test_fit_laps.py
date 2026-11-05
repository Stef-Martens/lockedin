import pytest
from conftest import get_activity, read
from sqlalchemy import text

from lockedin.fit.importer import import_fit
from lockedin.fit.parse import parse_fit, parse_fit_activities

SAMPLE = "watch_interval_run.fit"


def lap_rows(conn, activity_id):
    return conn.execute(text("select laps from activities where id = :i"), {"i": activity_id}).scalar()


def verdict_for(conn, activity_id):
    conn.execute(text("insert into workout_verdicts (activity_id, body) values (:i, 'old')"), {"i": activity_id})


def verdict_count(conn, activity_id):
    return conn.execute(text("select count(*) from workout_verdicts where activity_id = :i"), {"i": activity_id}).scalar()


def test_laps_are_parsed():
    laps = parse_fit(read(SAMPLE)).laps
    assert [lap["step_index"] for lap in laps] == [0, 1, 2, 1, 2, 1, 2, 4]
    assert [lap["intensity"] for lap in laps] == [
        "warmup", "active", "recovery", "active", "recovery", "active", "recovery", "cooldown"]
    assert [lap["start_s"] for lap in laps][:3] == [0, 600, 1080]
    block = laps[1]
    assert (block["timer_s"], block["elapsed_s"], block["avg_hr"]) == (480, 480, 164)
    assert 1000 / block["avg_speed"] == pytest.approx(331, abs=0.5)
    assert block["distance_m"] == pytest.approx(480 * 1000 / 331, rel=0.001)
    assert block["trigger"] == "manual"
    assert laps[0]["avg_hr"] == 135 and laps[0]["timer_s"] == 600


def test_multisport_laps_stay_with_their_leg():
    ride, run = parse_fit_activities(read("watch_brick.fit"))
    assert [lap["start_s"] for lap in ride.laps] == [0]
    assert ride.laps[0]["timer_s"] == 3600
    assert [lap["start_s"] for lap in run.laps] == [0]  # from the run's own start, not the file's
    assert run.laps[0]["timer_s"] == 1500


def test_no_laps_is_empty(tmp_path):
    from datetime import UTC, datetime

    from fit_tool.fit_file_builder import FitFileBuilder
    from fit_tool.profile.messages.record_message import RecordMessage
    from fit_tool.profile.messages.session_message import SessionMessage
    from fit_tool.profile.profile_type import Sport, SubSport

    t0 = int(datetime(2026, 11, 1, 8, tzinfo=UTC).timestamp() * 1000)
    b = FitFileBuilder(auto_define=True, min_string_size=50)
    for t in range(0, 120, 10):
        r = RecordMessage()
        r.timestamp, r.heart_rate = t0 + t * 1000, 140
        b.add(r)
    s = SessionMessage()
    s.start_time, s.timestamp, s.sport, s.sub_sport = t0, t0 + 120_000, Sport.RUNNING, SubSport.STREET
    s.total_elapsed_time = s.total_timer_time = 120
    b.add(s)
    out = tmp_path / "x.fit"
    b.build().to_file(str(out))
    assert parse_fit(out.read_bytes()).laps == []
    assert [lap["step_index"] for lap in parse_fit(read("watch_run.fit")).laps] == [None]


def test_import_stores_laps(conn):
    r = import_fit(conn, read(SAMPLE), "a.fit", "healthfit")
    stored = lap_rows(conn, r.activity_id)
    assert len(stored) == 8 and stored[1]["step_index"] == 1 and stored[1]["avg_hr"] == 164


def test_known_file_fills_null_laps_and_deletes_the_verdict(conn):
    r = import_fit(conn, read(SAMPLE), "a.fit", "healthfit")
    conn.execute(text("update activities set laps = null where id = :i"), {"i": r.activity_id})
    verdict_for(conn, r.activity_id)
    again = import_fit(conn, read(SAMPLE), "a.fit", "healthfit")
    assert again.status == "duplicate" and again.activity_id == r.activity_id
    assert len(lap_rows(conn, r.activity_id)) == 8
    assert verdict_count(conn, r.activity_id) == 0


def test_known_multisport_file_fills_each_leg(conn):
    r = import_fit(conn, read("watch_brick.fit"), "b.fit", "healthfit")
    conn.execute(text("update activities set laps = null"))
    assert import_fit(conn, read("watch_brick.fit"), "b.fit", "healthfit").status == "duplicate"
    rows = conn.execute(text("select source_ref, laps from activities order by id")).all()
    assert len(rows) == 2 and all(len(laps) == 1 for _, laps in rows)
    assert get_activity(conn, r.activity_id).laps[0]["timer_s"] == 3600


def test_known_file_with_laps_is_not_read_again(conn, monkeypatch):
    import lockedin.fit.importer as imp

    import_fit(conn, read(SAMPLE), "a.fit", "healthfit")

    def boom(data):
        raise AssertionError("parsed again")

    monkeypatch.setattr(imp, "parse_fit_activities", boom)
    assert import_fit(conn, read(SAMPLE), "a.fit", "healthfit").status == "duplicate"


def test_filling_laps_without_steps_keeps_the_verdict(conn):
    r = import_fit(conn, read("watch_run.fit"), "a.fit", "healthfit")
    conn.execute(text("update activities set laps = null where id = :i"), {"i": r.activity_id})
    verdict_for(conn, r.activity_id)
    assert import_fit(conn, read("watch_run.fit"), "a.fit", "healthfit").status == "duplicate"
    assert lap_rows(conn, r.activity_id) is not None
    assert verdict_count(conn, r.activity_id) == 1


def test_a_failure_filling_laps_is_still_a_duplicate(conn, monkeypatch):
    import lockedin.fit.importer as imp

    r = import_fit(conn, read(SAMPLE), "a.fit", "healthfit")
    conn.execute(text("update activities set laps = null where id = :i"), {"i": r.activity_id})
    verdict_for(conn, r.activity_id)

    def boom(data):
        raise RuntimeError("weird")

    monkeypatch.setattr(imp, "parse_fit_activities", boom)
    again = import_fit(conn, read(SAMPLE), "a.fit", "healthfit")
    assert again.status == "duplicate" and lap_rows(conn, r.activity_id) is None
    assert verdict_count(conn, r.activity_id) == 1  # and the transaction still works
