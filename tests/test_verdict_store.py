from datetime import UTC, datetime, timedelta

from focus_helpers import add_session
from sqlalchemy import text

from lockedin.verdict import store

NOW = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)
START = datetime(2026, 11, 3, 17, 0, tzinfo=UTC)


def add_item(conn, day: str, sport: str = "run", title: str = "Easy run") -> int:
    return conn.execute(text("insert into agenda_items (day, sport, title) values (:d, :s, :t) returning id"),
                        {"d": day, "s": sport, "t": title}).scalar_one()


def row(label: str | None):
    return type("R", (), {"label": label})()


def test_latest_skips_walks_and_superseded(conn):
    real = add_session(conn, "run", START, 1800)
    add_session(conn, "other", START + timedelta(hours=2), 1800, sub_type="walking")
    add_session(conn, "run", START + timedelta(hours=3), 1800, superseded_by=real)
    assert store.latest_activity(conn, NOW).id == real
    assert store.counted_activity(conn, real).id == real
    assert store.counted_activity(conn, real + 1) is None


def test_latest_is_none_without_workouts(conn):
    assert store.latest_activity(conn, NOW) is None


def test_claim_only_once(conn):
    a = add_session(conn, "run", START, 1800)
    assert store.claim(conn, a, None, NOW)
    assert not store.claim(conn, a, None, NOW)


def test_claim_free_after_six_minutes(conn):
    a = add_session(conn, "run", START, 1800)
    assert store.claim(conn, a, None, NOW)
    assert not store.claim(conn, a, None, NOW + timedelta(minutes=5, seconds=59))
    assert store.claim(conn, a, None, NOW + timedelta(minutes=6, seconds=1))


def test_failed_waits_fifteen_minutes(conn):
    a = add_session(conn, "run", START, 1800)
    assert store.claim(conn, a, None, NOW)
    store.fail(conn, a, NOW)
    assert not store.claim(conn, a, None, NOW + timedelta(minutes=14, seconds=59))
    assert store.claim(conn, a, None, NOW + timedelta(minutes=15, seconds=1))


def test_written_not_claimable_without_rewrite(conn):
    a = add_session(conn, "run", START, 1800)
    assert store.claim(conn, a, None, NOW)
    store.save(conn, a, "unplanned", "Nice run.", "m", NOW)
    later = NOW + timedelta(hours=1)
    assert not store.claim(conn, a, None, later)
    assert store.claim(conn, a, None, later, rewrite=True)
    assert store.read(conn, a).body == "Nice run."  # still there until the new one is saved


def test_stale_rewrite_cannot_claim_right_after_save(conn):
    a = add_session(conn, "run", START, 1800)
    assert store.claim(conn, a, None, NOW)
    store.save(conn, a, "unplanned", "Nice run.", "m", NOW)
    assert store.claim(conn, a, None, NOW + timedelta(hours=1), rewrite=True)
    store.save(conn, a, "on_plan", "Good.", "m", NOW + timedelta(hours=1))
    assert not store.claim(conn, a, None, NOW + timedelta(hours=1), rewrite=True)


def test_save_clears_failure(conn):
    a = add_session(conn, "run", START, 1800)
    store.claim(conn, a, None, NOW)
    store.fail(conn, a, NOW)
    store.save(conn, a, "close", "Fine.", "m", NOW)
    r = store.read(conn, a)
    assert r.failed_at is None and r.label == "close" and r.written_at == NOW


def test_up_to_date(conn):
    plan = {"sport": "run"}
    assert not store.up_to_date(row("unplanned"), plan)
    assert store.up_to_date(row("unplanned"), None)
    assert store.up_to_date(row("on_plan"), plan)
    assert not store.up_to_date(row("close"), None)
    assert store.up_to_date(row("off_plan"), {"sport": "run", "id": 99})  # a swapped item stays true


def test_rest_item_is_not_a_plan(conn):
    assert not store.is_plan({"sport": "rest"})
    assert not store.is_plan(None)
    assert store.is_plan({"sport": "run"})
    assert store.up_to_date(row("unplanned"), {"sport": "rest"})
    assert not store.up_to_date(row("on_plan"), {"sport": "rest"})


def test_ticking_item_uses_the_local_day(conn):
    # 23:30 UTC on the 3rd is 00:30 on the 4th in Brussels
    a = add_session(conn, "run", datetime(2026, 11, 3, 23, 30, tzinfo=UTC), 1800)
    add_item(conn, "2026-11-03", title="Wrong day")
    item = add_item(conn, "2026-11-04")
    got = store.ticking_item(conn, NOW, store.counted_activity(conn, a))
    assert got["id"] == item and got["activity_id"] == a


def test_ticking_item_none_when_nothing_ticks(conn):
    a = add_session(conn, "run", START, 1800)
    assert store.ticking_item(conn, NOW, store.counted_activity(conn, a)) is None


def test_item_deleted_sets_item_id_null(conn):
    a = add_session(conn, "run", START, 1800)
    item = add_item(conn, "2026-11-03")
    store.claim(conn, a, item, NOW)
    conn.execute(text("delete from agenda_items where id = :i"), {"i": item})
    assert store.read(conn, a).item_id is None


def test_coach_cannot_read_verdicts(conn):
    assert not conn.execute(text("select has_table_privilege('coach_ro', 'workout_verdicts', 'select')")).scalar()
