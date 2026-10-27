from datetime import UTC, datetime

import pytest
from conftest import count, owner_headers
from sqlalchemy import text

from lockedin.agenda.detail import _gym_rows
from lockedin.hevy.importer import e1rm, import_hevy
from lockedin.hevy.parse import HevySet, parse_hevy_csv
from lockedin.plan.routines import routine

HEADER = "title,start_time,end_time,exercise_title,set_index,set_type,weight_kg,reps\n"
BENCH, FLY = "Bench Press (Barbell)", "Chest Fly (Machine)"


def push(start="20 Oct 2026, 18:00", end="20 Oct 2026, 19:10", title="Push", back_off_kg=60):
    rows = [(BENCH, i, 80, 8) for i in range(3)] + [(FLY, i, 40, 12) for i in range(2)]
    rows += [(BENCH, i, back_off_kg, 12) for i in range(2)]
    return HEADER + "".join(f'"{title}","{start}","{end}","{n}",{i},normal,{kg},{r}\n' for n, i, kg, r in rows)


def test_an_exercise_done_again_later_is_its_own_block():
    (w,) = parse_hevy_csv(push()).workouts
    assert [(s.exercise_title, s.exercise_order, s.set_index) for s in w.sets] == [
        (BENCH, 0, 0), (BENCH, 0, 1), (BENCH, 0, 2), (FLY, 1, 0), (FLY, 1, 1), (BENCH, 2, 0), (BENCH, 2, 1)]


def test_set_index_fallback_counts_within_the_block():
    csv = push().replace("set_index,", "set_no,")
    (w,) = parse_hevy_csv(csv).workouts
    assert [s.set_index for s in w.sets] == [0, 1, 2, 0, 1, 0, 1]


def test_a_lift_done_twice_is_two_routine_exercises_and_matched_in_order(conn):
    import_hevy(conn, parse_hevy_csv(push()))
    r = routine(conn, datetime(2026, 10, 21, tzinfo=UTC), "Push")
    assert [(e.name, e.sets) for e in r.exercises] == [(BENCH, 3), (FLY, 2), (BENCH, 2)]
    plan = [{"exercise": BENCH, "sets": 3, "reps": "8", "weight_kg": 80, "kind": "routine"},
            {"exercise": FLY, "sets": 2, "reps": "12", "weight_kg": 40, "kind": "routine"},
            {"exercise": BENCH, "sets": 2, "reps": "12", "weight_kg": 60, "kind": "routine"}]
    rows = _gym_rows(conn, plan, r.activity_id)
    assert [(x["exercise"], x["status"], [s["kg"] for s in x["done"]]) for x in rows] == [
        (BENCH, "done", [80, 80, 80]), (FLY, "done", [40, 40]), (BENCH, "done", [60, 60])]


def test_updating_a_workout_with_a_repeated_lift_replaces_its_sets(conn):
    import_hevy(conn, parse_hevy_csv(push()))
    r = import_hevy(conn, parse_hevy_csv(push(back_off_kg=65)))
    assert (r.new, r.updated) == (0, 1) and count(conn, "gym_sets") == 7
    assert conn.execute(text("select exercise_order, weight_kg from gym_sets where set_index = 0 order by exercise_order")
                        ).all() == [(0, 80), (1, 40), (2, 65)]


def titles(conn):
    return conn.execute(text("select w.title, a.start_at from gym_workouts w join activities a on a.id = w.activity_id "
                             "order by a.start_at, w.title")).all()


def test_moving_the_start_time_in_hevy_updates_in_place(conn):
    import_hevy(conn, parse_hevy_csv(push()))
    r = import_hevy(conn, parse_hevy_csv(push(start="20 Oct 2026, 18:20")))
    assert (r.new, r.updated, r.unchanged) == (0, 1, 0)
    assert titles(conn) == [("Push", datetime(2026, 10, 20, 16, 20, tzinfo=UTC))]
    assert count(conn, "gym_sets") == 7
    assert import_hevy(conn, parse_hevy_csv(push(start="20 Oct 2026, 18:20"))).unchanged == 1


def test_moved_without_end_times_matches_within_two_hours_on_the_same_day(conn):
    def csv(start):
        return f'title,start_time,exercise_title,weight_kg,reps\n"Push","{start}","{BENCH}",80,8\n'
    import_hevy(conn, parse_hevy_csv(csv("20 Oct 2026, 18:00")))
    assert import_hevy(conn, parse_hevy_csv(csv("20 Oct 2026, 19:30"))).updated == 1
    assert count(conn, "gym_workouts") == 1
    assert import_hevy(conn, parse_hevy_csv(csv("21 Oct 2026, 07:30"))).new == 1  # next day: another workout


def test_same_title_later_the_same_day_is_another_workout(conn):
    two = push() + push(start="20 Oct 2026, 20:00", end="20 Oct 2026, 21:00").split("\n", 1)[1]
    assert import_hevy(conn, parse_hevy_csv(push())).new == 1
    r = import_hevy(conn, parse_hevy_csv(two))
    assert (r.new, r.unchanged) == (1, 1) and count(conn, "gym_workouts") == 2


def test_two_workouts_starting_the_same_minute_dont_overwrite_each_other(conn):
    both = push() + push(title="Abs").split("\n", 1)[1]
    r = import_hevy(conn, parse_hevy_csv(both))
    assert r.new == 2
    again = import_hevy(conn, parse_hevy_csv(both))
    assert (again.new, again.updated, again.unchanged) == (0, 0, 2)
    assert [t for t, _ in titles(conn)] == ["Abs", "Push"]


def test_a_new_workout_at_the_same_minute_as_one_in_the_db_is_added(conn):
    import_hevy(conn, parse_hevy_csv(push()))
    both = push() + push(title="Abs").split("\n", 1)[1]
    r = import_hevy(conn, parse_hevy_csv(both))
    assert (r.new, r.unchanged) == (1, 1)
    assert [t for t, _ in titles(conn)] == ["Abs", "Push"]


def s(name="Squat (Barbell)", kg=100.0, reps=5, set_type="normal"):
    return HevySet(name, 0, 0, set_type, kg, reps, None, None, None, None, None)


def test_e1rm_only_for_strength_range_sets():
    assert e1rm(s(reps=12)) == pytest.approx(140)
    assert e1rm(s(reps=13)) is None and e1rm(s(reps=30)) is None
    assert e1rm(s("Assisted Pull Up", kg=30, reps=8)) is None
    assert e1rm(s("Pull Up (Assisted)", kg=30, reps=8)) is None


def test_hevy_upload_too_large_is_rejected_even_without_content_length(client, monkeypatch):
    import dataclasses

    import lockedin.routes.hevy as route
    small = dataclasses.replace(route.get_settings(), max_upload_bytes=100)
    monkeypatch.setattr(route, "get_settings", lambda: small)
    files = {"file": ("hevy.csv", push().encode(), "text/csv")}
    r = client.post("/api/hevy/upload", files=files, headers=owner_headers())
    assert r.status_code == 413


def test_migration_clears_stored_e1rm_of_high_rep_and_assisted_sets(conn):
    from conftest import ROOT
    csv = (HEADER + f'"Mix","20 Oct 2026, 18:00","20 Oct 2026, 19:00","{BENCH}",0,normal,60,15\n'
           f'"Mix","20 Oct 2026, 18:00","20 Oct 2026, 19:00","{BENCH}",1,normal,80,8\n'
           '"Mix","20 Oct 2026, 18:00","20 Oct 2026, 19:00","Assisted Dip",0,normal,20,8\n')
    import_hevy(conn, parse_hevy_csv(csv))
    conn.execute(text("update gym_sets set e1rm = weight_kg * (1 + reps / 30.0)"))  # as the old code stored them
    conn.connection.driver_connection.execute(
        (ROOT / "supabase/migrations/20261028000001_ingest_fixes.sql").read_text().split("\n\n")[0])
    rows = conn.execute(text("select reps, e1rm from gym_sets order by id")).all()
    assert rows[0].e1rm is None and rows[1].e1rm == pytest.approx(101.33, abs=0.01) and rows[2].e1rm is None
