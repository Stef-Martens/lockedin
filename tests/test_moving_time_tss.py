from datetime import UTC, datetime

import pytest
from conftest import MIGRATIONS
from focus_helpers import add_session
from sqlalchemy import text

from lockedin.fitness import recompute_training_load


def test_tss_counts_moving_time_not_elapsed(conn):
    conn.execute(text("insert into ftp_history (effective_from, ftp) values ('2026-01-01', 250)"))
    rid = add_session(conn, "bike", datetime(2026, 10, 20, 17, tzinfo=UTC), 4200, source="zwift", np=200)
    conn.execute(text("update activities set moving_s = 3600 where id = :i"), {"i": rid})
    recompute_training_load(conn)
    assert conn.execute(text("select tss from activities where id = :i"), {"i": rid}).scalar() == pytest.approx(64.0)


def test_tss_falls_back_to_elapsed(conn):
    conn.execute(text("insert into ftp_history (effective_from, ftp) values ('2026-01-01', 250)"))
    rid = add_session(conn, "bike", datetime(2026, 10, 20, 17, tzinfo=UTC), 3600, source="zwift", np=200)
    conn.execute(text("update activities set moving_s = null where id = :i"), {"i": rid})
    recompute_training_load(conn)
    assert conn.execute(text("select tss from activities where id = :i"), {"i": rid}).scalar() == pytest.approx(64.0)


def test_migration_rescores_stored_rides_on_moving_time(conn):
    rid = add_session(conn, "bike", datetime(2026, 10, 20, 17, tzinfo=UTC), 4200, source="zwift", np=200)
    conn.execute(text("update activities set moving_s = 3600, if_ = 0.8, tss = 74.7 where id = :i"), {"i": rid})
    sql = next(m for m in MIGRATIONS if m.name.endswith("_ftp_history.sql")).read_text()
    for _ in range(2):  # re-runnable
        conn.connection.driver_connection.execute(sql)
    assert conn.execute(text("select tss from activities where id = :i"), {"i": rid}).scalar() == pytest.approx(64.0)
