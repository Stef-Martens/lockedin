from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from focus_helpers import add_gym, add_session
from sqlalchemy import text

from lockedin.agenda import actual as act
from lockedin.agenda.detail import _gym_rows
from lockedin.plan.build import build_plan, progression

NOW = datetime(2026, 10, 29, 20, 0, tzinfo=UTC)
BENCH, OHP = "Bench Press (Barbell)", "Overhead Press (Dumbbell)"


def test_a_goal_lift_moves_up_on_its_best_three_sets():
    sets = [(80, 12), (80, 12), (80, 12), (80, 9)]
    assert progression(sets, "barbell", "single", False)["change"] == "same"
    assert progression(sets, "barbell", "single", False, ready_on=3)["change"] == "up"


def test_goal_lift_is_marked_and_judged_with_its_extra_set(conn):
    conn.execute(text("insert into goals (text, area, exercise, status) values ('Bench 100 kg', 'gym', :e, 'active')"), {"e": BENCH})
    add_gym(conn, datetime(2026, 10, 24, 17, tzinfo=UTC), [(BENCH, 80, 12, "normal")] * 3 + [(BENCH, 80, 10, "normal")]
            + [(OHP, 40, 10, "normal")] * 3, title="Push")
    items = {i["exercise"]: i for i in build_plan(conn, NOW, "Push")["items"]}
    assert items[BENCH]["change"] == "up" and items[BENCH]["goal_extra"] is True and items[BENCH]["sets"] == 4
    assert items[OHP]["goal_extra"] is False


def test_gym_tick_allows_skipping_the_goal_set(conn):
    aid = add_gym(conn, NOW, [(BENCH, 85, 8, "normal")] * 3, title="Push")
    plan = [{"exercise": BENCH, "sets": 4, "reps": "8–12", "weight_kg": 85, "goal_extra": True, "kind": "routine"}]
    assert _gym_rows(conn, plan, aid)[0]["status"] == "done"


def test_the_same_exercise_twice_is_matched_in_order(conn):
    aid = add_gym(conn, NOW, [(BENCH, 80, 8, "normal")] * 3 + [(OHP, 40, 10, "normal")] * 3, title="Push")
    ex = conn.execute(text("select id from exercises where name = :n"), {"n": BENCH}).scalar_one()
    for i in range(2):  # back-off sets at the end, logged as a second Bench block
        conn.execute(text("insert into gym_sets (workout_id, exercise_id, exercise_order, set_index, set_type, weight_kg, reps) "
                          "values (:w, :e, 2, :i, 'normal', 60, 12)"), {"w": aid, "e": ex, "i": 10 + i})
    plan = [{"exercise": BENCH, "sets": 3, "reps": "8–12", "weight_kg": 80, "kind": "routine"},
            {"exercise": OHP, "sets": 3, "reps": "8–12", "weight_kg": 40, "kind": "routine"},
            {"exercise": BENCH, "sets": 2, "reps": "12", "weight_kg": 60, "kind": "routine"}]
    rows = _gym_rows(conn, plan, aid)
    assert [(r["exercise"], r["status"], len(r["done"])) for r in rows] == [(BENCH, "done", 3), (OHP, "done", 3), (BENCH, "done", 2)]


def _parts(start, end):
    return [{"label": "Interval 1", "start_s": start, "end_s": end, "from_frac": 0.9, "to_frac": 0.9, "work": True}]


def test_a_ride_sampled_every_3_seconds_still_covers_the_interval():
    t = list(range(0, 1800, 3))
    s = SimpleNamespace(t_offset=t, power=[151] * len(t), hr=None, cadence=None)
    rows, on = act.zwift_parts(_parts(600, 1200), s, 168)
    assert rows[0]["avg_w"] == 151 and rows[0]["status"] == "on_target" and on is True


def _run(points):
    t, d, v = zip(*points)
    return SimpleNamespace(t_offset=list(t), distance=list(d), speed=list(v), hr=None)


def test_a_stop_doesnt_slow_the_split():
    pts, dist, now = [], 0.0, 0
    while dist < 2000:
        if now == 400:  # a 60 s stop at a crossing, mid km 2
            for _ in range(60):
                pts.append((now, dist, 0.0))
                now += 1
        dist += 1000 / 300
        now += 1
        pts.append((now, dist, 1000 / 300))
    splits = act.splits(_run(pts), (None, None))
    assert [s["pace"] for s in splits] == [pytest.approx(300, abs=2)] * 2


def test_a_gps_gap_gives_no_absurd_split():
    pts = [(t, t * 1000 / 300, 1000 / 300) for t in range(0, 961)]  # 3.2 km at 5:00/km
    pts.append((961 + 660, 5400.0, 1000 / 300))  # 11 minutes without signal, then 2.2 km further on
    pts += [(1621 + k, 5400 + k * 1000 / 300, 1000 / 300) for k in range(1, 400)]
    splits = act.splits(_run(pts), (None, None))
    assert all(s["pace"] >= 120 for s in splits)
    assert splits[3]["pace"] == pytest.approx(300, abs=5) and splits[4]["pace"] == pytest.approx(300, abs=5)


def test_an_auto_paused_run_doesnt_count_the_pause():
    pts = [(t, t * 3.0, 3.0) for t in range(0, 301)]  # 900 m at 3 m/s
    pts += [(300 + 120 + k, 900 + 3 + k * 3.0, 3.0) for k in range(0, 200)]  # watch paused 2 minutes, no samples
    splits = act.splits(_run(pts), (None, None))
    assert splits[0]["pace"] == pytest.approx(333, abs=3)
