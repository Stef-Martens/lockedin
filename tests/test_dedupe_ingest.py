from itertools import permutations

import pytest
from conftest import get_activity, read, stream, superseded_by
from sqlalchemy import text

from lockedin.fit.importer import import_fit
from lockedin.hevy.importer import import_hevy
from lockedin.hevy.parse import parse_hevy_csv


def imp(conn, names):
    return {n: import_fit(conn, read(n), n, None).activity_id for n in names}


@pytest.mark.parametrize("order", [("zwift_run.fit", "watch_indoor_run.fit"), ("watch_indoor_run.fit", "zwift_run.fit")])
def test_zwift_run_replaces_the_watch_indoor_run(conn, order):
    ids = imp(conn, order)
    assert get_activity(conn, ids["zwift_run.fit"]).sport == "run"
    assert superseded_by(conn, ids["watch_indoor_run.fit"]) == ids["zwift_run.fit"]
    assert superseded_by(conn, ids["zwift_run.fit"]) is None


def test_zwift_run_leaves_a_watch_ride_alone(conn):
    ids = imp(conn, ["zwift_run.fit", "watch_indoor_cycle.fit"])
    conn.execute(text("update activities set start_at = '2026-10-21 17:58Z', end_at = '2026-10-21 18:45Z' where id = :i"),
                 {"i": ids["watch_indoor_cycle.fit"]})
    from lockedin.dedupe import resolve_overlaps
    resolve_overlaps(conn, ids["zwift_run.fit"])
    assert superseded_by(conn, ids["watch_indoor_cycle.fit"]) is None


@pytest.mark.parametrize("order", list(permutations(["zwift_ride_no_hr.fit", "watch_indoor_cycle.fit",
                                                     "watch_indoor_cycle_tail.fit"])))
def test_hr_comes_from_the_watch_file_covering_most_of_the_ride(conn, order):
    ids = imp(conn, order)
    ride = get_activity(conn, ids["zwift_ride_no_hr.fit"])
    assert superseded_by(conn, ids["watch_indoor_cycle.fit"]) == ride.id
    assert superseded_by(conn, ids["watch_indoor_cycle_tail.fit"]) == ride.id
    assert ride.hr_merged_from == ids["watch_indoor_cycle.fit"]
    assert stream(conn, ride.id).hr[0] == pytest.approx(129, abs=1) and ride.avg_hr > 120


def no_end_legs(start):
    return f'title,start_time,exercise_title,weight_kg,reps\n"Legs","{start}","Squat (Barbell)",100,5\n'


def test_a_watch_workout_shows_again_when_the_gym_workout_moves_off_it(conn):
    import_hevy(conn, parse_hevy_csv(no_end_legs("24 Oct 2026, 19:00")))  # 17:00–18:00Z
    wid = import_fit(conn, read("watch_strength.fit"), "s.fit", None).activity_id  # 17:05–17:55Z
    gym = conn.execute(text("select activity_id from gym_workouts")).scalar_one()
    assert superseded_by(conn, wid) == gym
    r = import_hevy(conn, parse_hevy_csv(no_end_legs("24 Oct 2026, 20:30")))  # moved in Hevy: 18:30–19:30Z
    assert r.updated == 1
    assert superseded_by(conn, wid) is None


def test_a_freed_watch_workout_goes_to_another_overlapping_primary(conn):
    two = no_end_legs("24 Oct 2026, 19:00") + '"Core","24 Oct 2026, 19:10","Plank",,\n'
    import_hevy(conn, parse_hevy_csv(two))
    wid = import_fit(conn, read("watch_strength.fit"), "s.fit", None).activity_id
    legs, core = conn.execute(text("select activity_id from gym_workouts order by title desc")).scalars().all()
    assert superseded_by(conn, wid) in (legs, core)
    conn.execute(text("update activities set superseded_by = :l where id = :w"), {"l": legs, "w": wid})
    moved = no_end_legs("24 Oct 2026, 20:30") + '"Core","24 Oct 2026, 19:10","Plank",,\n'
    import_hevy(conn, parse_hevy_csv(moved))
    assert superseded_by(conn, wid) == core
