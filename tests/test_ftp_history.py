from datetime import UTC, date, datetime

import pytest
from conftest import MIGRATIONS, owner_headers
from focus_helpers import add_session
from sqlalchemy import text

from lockedin.app import app
from lockedin.fitness import EstimatedFtp, ftp_at, known_ftp_at
from lockedin.routes.overview import get_now

H = owner_headers()
NOW = datetime(2026, 10, 27, 23, 30, tzinfo=UTC)  # already the 28th in Brussels (CET)


@pytest.fixture
def clock():
    app.dependency_overrides[get_now] = lambda: NOW


def history(conn):
    return [tuple(r) for r in conn.execute(text("select effective_from, ftp from ftp_history order by 1"))]


def test_ftp_at_uses_the_row_in_effect(conn):
    conn.execute(text("insert into ftp_history (effective_from, ftp) values ('2026-09-01', 220), ('2026-10-15', 240)"))
    assert ftp_at(conn, datetime(2026, 10, 1, 8, tzinfo=UTC)) == 220
    assert ftp_at(conn, datetime(2026, 10, 15, 6, tzinfo=UTC)) == 240
    assert not isinstance(ftp_at(conn, datetime(2026, 10, 15, 6, tzinfo=UTC)), EstimatedFtp)


def test_before_the_first_entry_the_estimate_applies(conn):
    conn.execute(text("insert into ftp_history (effective_from, ftp) values ('2026-10-15', 240)"))
    add_session(conn, "bike", datetime(2026, 8, 1, 8, tzinfo=UTC), 3600, source="zwift", best_20m_power=200)
    got = ftp_at(conn, datetime(2026, 9, 1, 8, tzinfo=UTC))
    assert got == pytest.approx(190) and isinstance(got, EstimatedFtp)
    assert known_ftp_at(conn, datetime(2026, 9, 1, 8, tzinfo=UTC)) is None


def test_a_cleared_ftp_means_estimate_from_then_on(conn):
    conn.execute(text("insert into ftp_history (effective_from, ftp) values ('2026-09-01', 220), ('2026-10-01', null)"))
    assert ftp_at(conn, datetime(2026, 10, 2, tzinfo=UTC)) is None
    assert ftp_at(conn, datetime(2026, 9, 2, tzinfo=UTC)) == 220


def test_bare_override_without_history_still_counts(conn):
    conn.execute(text("update profile set ftp_override = 168"))
    assert known_ftp_at(conn, datetime(2020, 1, 1, tzinfo=UTC)) == 168


def test_setting_ftp_starts_today_and_leaves_past_rides_alone(client, clean_db, clock):
    with clean_db.begin() as c:
        past = add_session(c, "bike", datetime(2026, 10, 20, 17, tzinfo=UTC), 3600, source="zwift", np=200)
        c.execute(text("update activities set tss = 55, if_ = 0.74 where id = :i"), {"i": past})
    r = client.put("/api/profile", json={"ftp_override": 250}, headers=H)
    assert r.status_code == 200 and r.json()["ftp_override"] == 250
    with clean_db.begin() as c:
        assert history(c) == [(date(2026, 10, 28), 250)]
        assert c.execute(text("select tss from activities where id = :i"), {"i": past}).scalar() == 55
    client.patch("/api/profile", json={"ftp_override": 260}, headers=H)  # same day again: one row, updated
    client.patch("/api/profile", json={"height_cm": 180}, headers=H)     # FTP not sent: untouched
    with clean_db.begin() as c:
        assert history(c) == [(date(2026, 10, 28), 260)]
        assert c.execute(text("select ftp_override from profile")).scalar() == 260


def test_first_history_row_keeps_an_older_bare_override(client, clean_db, clock):
    with clean_db.begin() as c:
        c.execute(text("update profile set ftp_override = 230"))
        add_session(c, "bike", datetime(2026, 6, 3, 17, tzinfo=UTC), 3600, source="zwift")
    client.patch("/api/profile", json={"ftp_override": 250}, headers=H)
    with clean_db.begin() as c:
        assert history(c) == [(date(2026, 6, 3), 230), (date(2026, 10, 28), 250)]


def test_clearing_ftp_records_it(client, clean_db, clock):
    client.patch("/api/profile", json={"ftp_override": 250}, headers=H)
    client.patch("/api/profile", json={"ftp_override": None}, headers=H)
    with clean_db.begin() as c:
        assert history(c) == [(date(2026, 10, 28), None)]


def test_migration_seeds_history_from_the_override(conn):
    conn.execute(text("update profile set ftp_override = 240"))
    add_session(conn, "run", datetime(2026, 3, 1, 23, 30, tzinfo=UTC), 1800)  # 2 March in Brussels
    sql = next(m for m in MIGRATIONS if m.name.endswith("_ftp_history.sql")).read_text()
    conn.connection.driver_connection.execute(sql)  # re-runnable
    assert history(conn) == [(date(2026, 3, 2), 240)]
