from datetime import UTC, date, datetime

import pytest
from conftest import owner_headers
from focus_helpers import add_gym, add_session
from sqlalchemy import text

from lockedin.coach.tools import execute_tool
from lockedin.goals.progress import goal_lift, progress

NOW = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)
BENCH = "Bench Press (Barbell)"


def goal(conn, text_, area="general", exercise=None, target=None, created=NOW):
    gid = conn.execute(text("insert into goals (text, area, exercise, target, created_at) values (:t, :a, :e, :g, :c) returning id"),
                       {"t": text_, "a": area, "e": exercise, "g": target, "c": created}).scalar_one()
    return dict(conn.execute(text("select * from goals where id = :i"), {"i": gid}).mappings().one())


def test_lift_goal_with_or_without_a_linked_exercise(conn):
    add_gym(conn, datetime(2026, 10, 20, 17, tzinfo=UTC), [(BENCH, 72, 10, "normal")])  # e1RM 96
    linked = goal(conn, "Bench 100 kg", "gym", exercise=BENCH)
    p = progress(conn, NOW, linked)
    assert p["label"] == "96 / 100 kg est. 1RM" and p["fraction"] == pytest.approx(0.96)
    loose = goal(conn, "Bench 100 kg by March 2027 at 80 kg bodyweight", "gym")
    assert goal_lift(conn, NOW, loose) == BENCH
    assert progress(conn, NOW, loose)["target"] == 100


def test_ftp_goal(conn):
    conn.execute(text("update profile set ftp_override = 168"))
    assert progress(conn, NOW, goal(conn, "FTP 200 W", "bike"))["label"] == "168 / 200 W"


def test_run_and_swim_distance_goals(conn):
    add_session(conn, "run", datetime(2026, 10, 10, 8, tzinfo=UTC), 2800, distance_m=8200)
    add_session(conn, "swim", datetime(2026, 10, 12, 8, tzinfo=UTC), 1800, distance_m=1500)
    assert progress(conn, NOW, goal(conn, "Run a 10K", "run"))["label"] == "8.2 / 10 km"
    assert progress(conn, NOW, goal(conn, "Swim 2 km", "swim"))["label"] == "1.5 / 2 km"


def test_body_goal_fills_from_the_value_when_set(conn):
    weight = conn.execute(text("select id from measurement_types where name = 'Weight'")).scalar_one()
    for d, v in ((date(2026, 9, 1), 82.0), (date(2026, 10, 20), 80.0)):
        conn.execute(text("insert into measurements (type_id, measured_on, value) values (:t, :d, :v)"),
                     {"t": weight, "d": d, "v": v})
    g = goal(conn, "Weight 78 kg", "body", created=datetime(2026, 9, 5, tzinfo=UTC))
    p = progress(conn, NOW, g)
    assert p["fraction"] == pytest.approx(0.5) and p["current"] == 80
    assert progress(conn, NOW, goal(conn, "Lose 5 kg", "body")) is None


def test_unmeasurable_goal(conn):
    assert progress(conn, NOW, goal(conn, "Feel fitter")) is None
    assert progress(conn, NOW, goal(conn, "Bench 100 kg", "gym")) is None  # no lift logged


def test_active_goals_endpoint_has_progress(client, clean_db):
    with clean_db.begin() as c:
        c.execute(text("update profile set ftp_override = 168"))
        goal(c, "FTP 200 W", "bike")
    goals = client.get("/api/goals/active", headers=owner_headers()).json()
    assert goals[0]["area"] == "bike" and goals[0]["progress"]["label"] == "168 / 200 W"


def test_save_goal_area_is_a_known_kind(clean_db):
    with clean_db.begin() as c:
        out, err = execute_tool("save_goal", {"action": "create", "text": "Faster", "area": "cardio"},
                                conn=c, engine=clean_db, now=NOW)
    assert err


@pytest.mark.parametrize("words, area", [
    ("Raise FTP by 20 W", "bike"), ("Add 10 kg to my bench", "gym"), ("Bench +10 kg", "gym"), ("FTP 4 W/kg", "bike"),
])
def test_relative_and_ratio_goals_get_no_bar(conn, words, area):
    conn.execute(text("update profile set ftp_override = 168"))
    add_gym(conn, datetime(2026, 10, 20, 17, tzinfo=UTC), [(BENCH, 72, 10, "normal")])
    assert progress(conn, NOW, goal(conn, words, area, exercise=BENCH if area == "gym" else None)) is None


def test_a_target_far_below_today_is_a_misread(conn):
    add_gym(conn, datetime(2026, 10, 20, 17, tzinfo=UTC), [(BENCH, 72, 10, "normal")])  # e1RM 96
    assert progress(conn, NOW, goal(conn, "Bench 40 kg", "gym", exercise=BENCH)) is None
    assert progress(conn, NOW, goal(conn, "Bench 30 kg for 10 reps", "gym", exercise=BENCH)) is None  # vs 72 × 10


def test_thousands_separators(conn):
    add_session(conn, "swim", datetime(2026, 10, 12, 8, tzinfo=UTC), 1800, distance_m=1200)
    for words in ("Swim 1.500 m", "Swim 1,500 m"):
        assert progress(conn, NOW, goal(conn, words, "swim"))["label"] == "1.2 / 1.5 km"


def test_arm_goals_use_both_arms(conn):
    ids = dict(conn.execute(text("select name, id from measurement_types")).all())
    for d, left, right in ((date(2026, 9, 1), 36.0, 37.0), (date(2026, 10, 20), 37.5, 38.5)):
        for name, v in (("Left arm", left), ("Right arm", right)):
            conn.execute(text("insert into measurements (type_id, measured_on, value) values (:t, :d, :v)"),
                         {"t": ids[name], "d": d, "v": v})
    p = progress(conn, NOW, goal(conn, "40 cm arms", "body", created=datetime(2026, 9, 5, tzinfo=UTC)))
    assert p["current"] == 38 and p["fraction"] == pytest.approx(1.5 / 3.5)  # from 36.5 (avg at goal time) toward 40
