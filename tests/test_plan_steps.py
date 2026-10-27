"""Load steps that scale with the weight, and lifts eased back in after weeks away from them."""

from datetime import timedelta

import pytest
from focus_helpers import add_gym, add_session
from sqlalchemy import text
from test_plan_build import BENCH, NOW, OHP, items_by

from lockedin.focus.suggest import weighted_pick
from lockedin.plan.build import build_plan, progression
from lockedin.plan.steps import eased, step_up


@pytest.mark.parametrize("kg, equipment, logging, step", [
    (40, "barbell", "pair", 2.5), (80, "barbell", "pair", 5), (140, "barbell", "pair", 7.5),
    (60, "dumbbell", "pair", 4), (12, "dumbbell", "pair", 4), (40, "dumbbell", "each", 2), (6, "dumbbell", "each", 2),
    (50, "machine", "pair", 5), (30, "cable", "pair", 2.5), (10, "other", "pair", 2.5),
])
def test_step_is_about_5_percent_on_the_equipment_grid(kg, equipment, logging, step):
    assert step_up(kg, equipment, logging) == step


def test_progression_steps_with_the_load():
    up = progression([(140, 12)] * 3, "barbell", "pair", False)
    assert (up["change"], up["weight_kg"]) == ("up", 147.5)


@pytest.mark.parametrize("kg, equipment, logging, cut, out", [
    (80, "barbell", "pair", 0.1, 70), (100, "barbell", "pair", 0.1, 90), (80, "barbell", "pair", 0.2, 62.5),
    (60, "dumbbell", "pair", 0.1, 52), (14, "dumbbell", "each", 0.1, 12), (50, "machine", "pair", 0.2, 40),
])
def test_eased_rounds_down_to_the_equipment(kg, equipment, logging, cut, out):
    assert eased(kg, equipment, logging, cut) == out


def _rides(conn, days):
    for d in days:
        add_session(conn, "bike", NOW - timedelta(days=d), 3600, source="zwift")


def test_lift_not_done_for_weeks_is_eased_even_without_a_break(conn):
    add_gym(conn, NOW - timedelta(days=43), [(BENCH, 80, 12, "normal")] * 3 + [(OHP, 40, 12, "normal")] * 3, title="A")
    _rides(conn, range(1, 42, 3))  # only Zwift since: no comeback
    plan = build_plan(conn, NOW, "A")
    bench = items_by(plan)[BENCH]
    assert plan["comeback"] is False
    assert (bench["change"], bench["weight_kg"], bench["reps"]) == ("eased", 70, "8–12")
    assert bench["reason"] == "Back after 6 weeks: lighter to ease in"


def test_two_months_away_takes_off_more(conn):
    add_gym(conn, NOW - timedelta(days=58), [(BENCH, 80, 12, "normal")] * 3, title="A")
    _rides(conn, range(1, 56, 3))
    assert items_by(build_plan(conn, NOW, "A"))[BENCH]["weight_kg"] == 62.5


def test_recent_lift_still_goes_up_next_to_a_stale_one(conn):
    add_gym(conn, NOW - timedelta(days=30), [(OHP, 40, 12, "normal")] * 3, title="A")
    add_gym(conn, NOW - timedelta(days=3), [(BENCH, 80, 12, "normal")] * 3, title="B")
    plan = items_by(build_plan(conn, NOW, "A"))
    assert plan[OHP]["change"] == "eased" and plan[OHP]["weight_kg"] == 36  # 20 + 20 → 18 + 18
    assert items_by(build_plan(conn, NOW, "B"))[BENCH]["change"] == "up"


def test_goal_lift_gets_no_extra_set_while_easing_in(conn):
    add_gym(conn, NOW - timedelta(days=43), [(BENCH, 80, 12, "normal")] * 3, title="A")
    _rides(conn, range(1, 42, 3))
    conn.execute(text("insert into goals (text, exercise) values ('Bench 100 kg', :e)"), {"e": BENCH})
    bench = items_by(build_plan(conn, NOW, "A"))[BENCH]
    assert bench["sets"] == 3 and bench["goal_extra"] is False


def test_comeback_keeps_its_flag_and_eases_stale_lifts(conn):
    add_gym(conn, NOW - timedelta(days=30), [(BENCH, 80, 12, "normal")] * 3, title="A")
    plan = build_plan(conn, NOW, "A")
    bench = items_by(plan)[BENCH]
    assert plan["comeback"] is True
    assert (bench["change"], bench["weight_kg"]) == ("welcome_back", 70)


def test_bodyweight_lift_eases_by_reps(conn):
    add_gym(conn, NOW - timedelta(days=43), [("Pull Up", None, 12, "normal")] * 3, title="A")
    _rides(conn, range(1, 42, 3))
    pull = items_by(build_plan(conn, NOW, "A"))["Pull Up"]
    assert (pull["change"], pull["weight_kg"], pull["reps"]) == ("eased", None, "10")


def test_suggested_weight_is_eased_for_a_lift_left_for_weeks(conn):
    add_gym(conn, NOW - timedelta(days=40), [(BENCH, 80, 12, "normal")] * 3, title="A")
    muscle = conn.execute(text("select muscle_key from library_muscles where exercise_name = :n and role = 'primary'"),
                          {"n": BENCH}).scalars().first()
    fresh = weighted_pick(conn, muscle, NOW - timedelta(days=30), "pair")
    stale = weighted_pick(conn, muscle, NOW, "pair")
    assert fresh["exercise"] == stale["exercise"] == BENCH
    assert (fresh["weight_kg"], stale["weight_kg"]) == (80, 70)  # 72 rounded down to the plates
