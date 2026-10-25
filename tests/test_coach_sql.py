import time

import pytest
from sqlalchemy import text

from lockedin.coach.sql import QueryRejected, check_query, run_readonly


@pytest.mark.parametrize("sql, cleaned", [
    ("select 1", "select 1"),
    ("with x as (select 1) select * from x;", "with x as (select 1) select * from x"),
    ("-- how many rides\nSELECT count(*) from activities", "-- how many rides\nSELECT count(*) from activities"),
])
def test_check_query_accepts_single_select(sql, cleaned):
    assert check_query(sql) == cleaned


@pytest.mark.parametrize("sql", [
    "delete from goals",
    "select 1; delete from goals",
    "set role postgres",
    "",
    "   ",
    "select 1 " + "x" * 5000,
    "/* sneaky */ update goals set text = 'x'",
])
def test_check_query_rejects(sql):
    with pytest.raises(QueryRejected):
        check_query(sql)


def test_runs_a_select(clean_db):
    with clean_db.begin() as c:
        c.execute(text("insert into goals (text) values ('Bench 100 kg')"))
    out = run_readonly(clean_db, "select id, text, status from goals")
    assert out["columns"] == ["id", "text", "status"]
    assert out["rows"] == [[1, "Bench 100 kg", "active"]]
    assert out["row_count"] == 1 and out["truncated"] is False


def test_keeps_duplicate_column_names_in_order(clean_db):
    out = run_readonly(clean_db, "select 1 as a, 2 as b, 3 as a")
    assert out["columns"] == ["a", "b", "a"] and out["rows"] == [[1, 2, 3]]


def test_private_tables_are_not_readable(clean_db):
    for sql in ["select * from fit_files", "select * from import_log", "select * from activity_streams",
                "select * from coach_messages", "select * from auth.users"]:
        with pytest.raises(QueryRejected):
            run_readonly(clean_db, sql)


def test_cannot_switch_role(clean_db):
    for sql in ["select set_config('role', 'postgres', true)",
                "select * from query_to_xml('select set_config(''role'',''postgres'',true)', true, true, '')"]:
        with pytest.raises(QueryRejected):
            run_readonly(clean_db, sql)


def test_cannot_write_even_through_a_cte(clean_db):
    with clean_db.begin() as c:
        c.execute(text("insert into goals (text) values ('keep me')"))
    with pytest.raises(QueryRejected):
        run_readonly(clean_db, "with d as (delete from goals returning *) select * from d")
    with clean_db.begin() as c:
        assert c.execute(text("select count(*) from goals")).scalar() == 1


def test_slow_queries_time_out_even_if_timeout_is_reset(clean_db):
    started = time.monotonic()
    with pytest.raises(QueryRejected, match="timeout"):
        run_readonly(clean_db, "select set_config('statement_timeout', '0', true), pg_sleep(6)")
    assert time.monotonic() - started < 4.5


def test_caps_rows(clean_db):
    out = run_readonly(clean_db, "select g from generate_series(1, 250) g")
    assert out["row_count"] == 200 and out["truncated"] is True and out["rows"][-1] == [200]


def test_caps_size(clean_db):
    out = run_readonly(clean_db, "select repeat('x', 1000) as filler from generate_series(1, 100)")
    assert out["truncated"] is True and out["row_count"] < 100


def test_dates_are_iso_strings_in_brussels_time(clean_db):
    out = run_readonly(clean_db, "select date '2026-10-25' as d, timestamptz '2026-10-25 10:00:00+00' as t")
    assert out["rows"] == [["2026-10-25", "2026-10-25T11:00:00+01:00"]]


def test_whitelisted_tables_are_readable(clean_db):
    for table in ["activities", "gym_workouts", "gym_sets", "exercises", "measurements", "measurement_types",
                  "muscles", "library_exercises", "library_muscles", "profile", "goals"]:
        run_readonly(clean_db, f"select * from {table} limit 1")
