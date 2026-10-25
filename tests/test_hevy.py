from datetime import UTC, datetime

import pytest
from conftest import SAMPLES, count, owner_headers, read, superseded_by
from sqlalchemy import text

from lockedin.fit.importer import import_fit
from lockedin.hevy.importer import import_hevy
from lockedin.hevy.parse import parse_hevy_csv


def sample(name: str) -> str:
    return (SAMPLES / name).read_bytes().decode("utf-8")


def test_parse_sample_counts():
    p = parse_hevy_csv(sample("hevy_sample.csv"))
    assert [w.title for w in p.workouts] == ["Push Day", "Pull Day", "Legs"]
    assert [len(w.sets) for w in p.workouts] == [8, 6, 4]
    assert p.skipped == []
    push = p.workouts[0]
    assert push.start_at == datetime(2026, 10, 20, 16, 0, tzinfo=UTC)  # 18:00 CEST
    assert push.end_at == datetime(2026, 10, 20, 17, 10, tzinfo=UTC)
    assert [s.exercise_order for s in push.sets] == [0, 0, 0, 0, 1, 1, 2, 2]
    assert push.sets[0].set_type == "warmup" and push.sets[3].rpe == 8.5
    assert push.sets[4].superset_id == "0" and push.sets[6].notes == "rope"
    assert p.workouts[1].sets[0].weight_kg is None and p.workouts[1].sets[0].reps == 10


def test_lbs_bom_crlf_reordered():
    p = parse_hevy_csv(sample("hevy_reordered_lbs.csv"))
    (w,) = p.workouts
    assert w.title == "Late Night" and len(w.sets) == 2
    assert w.sets[0].weight_kg == pytest.approx(45.36, abs=0.01)
    assert w.start_at == datetime(2026, 10, 25, 0, 30, tzinfo=UTC)  # ambiguous 02:30 → first occurrence


def test_missing_required_column_raises():
    with pytest.raises(ValueError, match="exercise_title"):
        parse_hevy_csv("title,start_time\nA,\"20 Oct 2026, 18:00\"\n")


def test_unparseable_row_is_skipped_with_reason():
    csv = ('title,start_time,exercise_title,weight_kg,reps\n'
           'A,"20 Oct 2026, 18:00",Squat,100,5\n'
           'A,"20 Oct 2026, 18:00",Squat,heavy,5\n'
           'B,not a date,Squat,100,5\n')
    p = parse_hevy_csv(csv)
    assert len(p.workouts) == 1 and len(p.workouts[0].sets) == 1
    assert [r for r, _ in p.skipped] == [3, 4]
    assert p.workouts[0].end_at == datetime(2026, 10, 20, 17, 0, tzinfo=UTC)  # no end_time → start + 1 h


def test_reimport_is_idempotent(conn):
    p = parse_hevy_csv(sample("hevy_sample.csv"))
    first = import_hevy(conn, p)
    assert (first.new, first.updated, first.unchanged) == (3, 0, 0)
    second = import_hevy(conn, parse_hevy_csv(sample("hevy_sample.csv")))
    assert (second.new, second.updated, second.unchanged) == (0, 0, 3)
    assert (count(conn, "gym_workouts"), count(conn, "gym_sets"), count(conn, "activities")) == (3, 18, 3)
    assert count(conn, "exercises") == 6


def test_edit_propagates(conn):
    import_hevy(conn, parse_hevy_csv(sample("hevy_sample.csv")))
    edited = sample("hevy_sample.csv").replace('"normal",100,5,,,7', '"normal",105,5,,,7')
    r = import_hevy(conn, parse_hevy_csv(edited))
    assert (r.new, r.updated, r.unchanged) == (0, 1, 2)
    weights = conn.execute(text("select weight_kg from gym_sets s join exercises e on e.id = s.exercise_id "
                                "where e.name = 'Squat (Barbell)' order by set_index")).scalars().all()
    assert weights == [60, 100, 100, 105] and count(conn, "gym_sets") == 18


def test_absent_workout_kept(conn):
    import_hevy(conn, parse_hevy_csv(sample("hevy_sample.csv")))
    only_legs = "\n".join(l for i, l in enumerate(sample("hevy_sample.csv").splitlines()) if i == 0 or '"Legs"' in l)
    r = import_hevy(conn, parse_hevy_csv(only_legs))
    assert (r.new, r.updated, r.unchanged) == (0, 0, 1)
    assert count(conn, "gym_workouts") == 3


def test_e1rm(conn):
    import_hevy(conn, parse_hevy_csv(sample("hevy_sample.csv")))
    rows = conn.execute(text("select set_type, weight_kg, reps, e1rm from gym_sets s join exercises e on e.id = s.exercise_id "
                             "where e.name = 'Squat (Barbell)' order by set_index")).all()
    assert rows[0].e1rm is None  # warmup
    assert rows[1].e1rm == pytest.approx(116.67, abs=0.01)  # 100 × (1 + 5/30)
    pull = conn.execute(text("select e1rm from gym_sets s join exercises e on e.id = s.exercise_id where e.name = 'Pull Up'")).scalars().all()
    assert set(pull) == {None}  # bodyweight, no weight


def test_activity_rows_are_gym(conn):
    import_hevy(conn, parse_hevy_csv(sample("hevy_sample.csv")))
    rows = conn.execute(text("select source, sport, duration_s from activities order by start_at")).all()
    assert [tuple(r) for r in rows] == [("hevy", "gym", 4200), ("hevy", "gym", 3600), ("hevy", "gym", 3300)]


@pytest.mark.parametrize("hevy_first", [True, False])
def test_watch_strength_superseded_by_hevy(conn, hevy_first):
    def hevy():
        import_hevy(conn, parse_hevy_csv(sample("hevy_sample.csv")))

    def watch():
        return import_fit(conn, read("watch_strength.fit"), "s.fit", None).activity_id

    if hevy_first:
        hevy(); wid = watch()
    else:
        wid = watch(); hevy()
    legs = conn.execute(text("select activity_id from gym_workouts where title = 'Legs'")).scalar()
    assert superseded_by(conn, wid) == legs


def test_upload_route(client):
    files = {"file": ("hevy.csv", read("hevy_sample.csv"), "text/csv")}
    r = client.post("/api/hevy/upload", files=files, headers=owner_headers())
    assert r.status_code == 200 and r.json() == {"new": 3, "updated": 0, "unchanged": 0, "skipped": []}
    assert client.post("/api/hevy/upload", files=files).status_code == 401


def test_upload_route_bad_csv(client):
    files = {"file": ("x.csv", b"foo,bar\n1,2\n", "text/csv")}
    r = client.post("/api/hevy/upload", files=files, headers=owner_headers())
    assert r.status_code == 422 and "Missing column" in r.json()["detail"]


def test_renamed_workout_updates_instead_of_duplicating(conn):
    import_hevy(conn, parse_hevy_csv(sample("hevy_sample.csv")))
    r = import_hevy(conn, parse_hevy_csv(sample("hevy_sample.csv").replace('"Legs"', '"Leg Day"')))
    assert (r.new, r.updated, r.unchanged) == (0, 1, 2)
    assert count(conn, "gym_workouts") == 3
    assert conn.execute(text("select title from gym_workouts order by activity_id")).scalars().all() == ["Push Day", "Pull Day", "Leg Day"]
