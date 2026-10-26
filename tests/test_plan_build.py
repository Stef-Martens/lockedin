from datetime import UTC, datetime, timedelta

import pytest
from focus_helpers import add_gym
from sqlalchemy import text

from lockedin.plan.build import build_plan, swap_item
from lockedin.plan.goals import goal_for
from lockedin.plan.routines import routines

NOW = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)
CHEST = "Chest - Schouders - Triceps"
BENCH, INCLINE, OHP = "Bench Press (Barbell)", "Incline Bench Press (Dumbbell)", "Overhead Press (Dumbbell)"


def day(d: int, month: int = 10) -> datetime:
    return datetime(2026, month, d, 17, 0, tzinfo=UTC)


def items_by(plan: dict) -> dict:
    return {i["exercise"]: i for i in plan["items"]}


def chest_day(conn, when, bench=(60, 8), incline=(50, 10), ohp=(40, 10), title=CHEST):
    add_gym(conn, when, [(BENCH, 40, 10, "warmup")] + [(BENCH, *bench, "normal")] * 3
            + [(INCLINE, *incline, "normal")] * 3 + [(OHP, *ohp, "normal")] * 3, title=title)


def test_routines_from_titles(conn):
    chest_day(conn, day(20))
    add_gym(conn, day(21), [("Lat Pulldown (Cable)", 60, 10, "normal")] * 3, title="Rug - Bicep")
    add_gym(conn, day(24), [(INCLINE, 50, 10, "normal")] * 2 + [(BENCH, 60, 8, "normal")] * 4, title=CHEST)
    add_gym(conn, NOW - timedelta(days=70), [(BENCH, 60, 8, "normal")], title="Old split")
    found = routines(conn, NOW)
    assert [r.title for r in found] == [CHEST, "Rug - Bicep"]
    assert [(e.name, e.sets) for e in found[0].exercises] == [(INCLINE, 2), (BENCH, 4)]


def test_progression_up_and_same(conn):
    add_gym(conn, day(24), [(BENCH, 80, 12, "normal")] * 3 + [(INCLINE, 60, 12, "normal")] * 3, title="A")
    add_gym(conn, day(23), [("Lat Pulldown (Cable)", 60, 12, "normal"), ("Lat Pulldown (Cable)", 60, 10, "normal")], title="B")
    add_gym(conn, day(22), [("Pull Up", None, 12, "normal")] * 3 + [("Triceps Dip", 10, 12, "normal")] * 3, title="C")
    a = items_by(build_plan(conn, NOW, "A"))
    assert (a[BENCH]["change"], a[BENCH]["weight_kg"]) == ("up", 82.5)
    assert (a[INCLINE]["weight_kg"], a[INCLINE]["dumbbell"]) == (64, "pair")
    assert a[BENCH]["last"] == [{"kg": 80, "reps": 12}] * 3
    b = items_by(build_plan(conn, NOW, "B"))
    assert (b["Lat Pulldown (Cable)"]["change"], b["Lat Pulldown (Cable)"]["weight_kg"]) == ("same", 60)
    c = items_by(build_plan(conn, NOW, "C"))
    assert (c["Pull Up"]["weight_kg"], c["Pull Up"]["reps"], c["Pull Up"]["change"]) == (None, "13", "up")
    assert (c["Triceps Dip"]["weight_kg"], c["Triceps Dip"]["change"]) == (12.5, "up")


def test_dumbbells_logged_per_hand(conn):
    conn.execute(text("update profile set dumbbell_weights = 'each'"))
    add_gym(conn, day(24), [("Lateral Raise (Dumbbell)", 12, 12, "normal")] * 3, title="A")
    item = items_by(build_plan(conn, NOW, "A"))["Lateral Raise (Dumbbell)"]
    assert (item["weight_kg"], item["dumbbell"]) == (14, "each")


def test_unmapped_exercise_stays_without_crashing(conn):
    add_gym(conn, day(24), [("Mystery Machine", 50, 10, "normal")] * 3 + [(BENCH, 60, 8, "normal")] * 3, title="A")
    item = items_by(build_plan(conn, NOW, "A"))["Mystery Machine"]
    assert item["kind"] == "routine" and item["weight_kg"] == 50 and item["muscle"] is None


def _stalled_ohp(conn):
    # Two strong early sessions, then four weaker ones within the last six weeks: a plateau.
    # Bench and incline keep improving, so only the overhead press is stuck.
    for d in (day(25, 8), day(1, 9)):
        chest_day(conn, d, bench=(55, 8), incline=(45, 10), ohp=(44, 12))
    for d in (day(20, 9), day(30, 9), day(10), day(20)):
        chest_day(conn, d, bench=(60, 8), incline=(50, 10), ohp=(40, 10))


def test_variety_swap_on_stalled_exercise(conn):
    _stalled_ohp(conn)
    plan = build_plan(conn, NOW, CHEST)
    swaps = [i for i in plan["items"] if i["kind"] == "swap"]
    assert len(swaps) == 1
    swap = swaps[0]
    assert swap["replaces"] == OHP and swap["muscle"] == "front_delt" and swap["suggested"] is True
    assert swap["exercise"] not in {BENCH, INCLINE, OHP}
    assert [i["exercise"] for i in plan["items"]][:3] == [BENCH, INCLINE, swap["exercise"]]


def test_goal_exercise_is_never_swapped(conn):
    _stalled_ohp(conn)
    conn.execute(text("insert into goals (text, exercise) values ('Overhead press 30 kg each', :e)"), {"e": OHP})
    plan = build_plan(conn, NOW, CHEST)
    assert not [i for i in plan["items"] if i["kind"] == "swap"]
    assert items_by(plan)[OHP]["goal"] == "Overhead press 30 kg each"


def test_adds_for_low_day_muscles(conn):
    chest_day(conn, day(20))
    plan = build_plan(conn, NOW, CHEST)
    adds = [i for i in plan["items"] if i["kind"] == "add"]
    assert 1 <= len(adds) <= 2
    assert "rear_delt" in {a["muscle"] for a in adds}
    assert all(a["suggested"] and a["reason"] for a in adds)
    assert plan["items"][-len(adds):] == adds  # extras come last

    conn.execute(text("update profile set avoid_muscles = '{rear_delt}'"))
    assert "rear_delt" not in {i["muscle"] for i in build_plan(conn, NOW, CHEST)["items"] if i["kind"] == "add"}


def test_day_muscles_secondary_not_expanded(conn):
    add_gym(conn, day(21), [("Seated Cable Row - V Grip (Cable)", 60, 10, "normal")] * 3
            + [("Lat Pulldown (Cable)", 60, 10, "normal")] * 3, title="Rug - Bicep")
    adds = [i for i in build_plan(conn, NOW, "Rug - Bicep")["items"] if i["kind"] == "add"]
    assert "side_delt" not in {a["muscle"] for a in adds} and "front_delt" not in {a["muscle"] for a in adds}


def test_never_suggest_is_respected(conn):
    chest_day(conn, day(20))
    first = {i["muscle"]: i["exercise"] for i in build_plan(conn, NOW, CHEST)["items"] if i["kind"] == "add"}
    conn.execute(text("update profile set never_exercises = :n"), {"n": [first["rear_delt"]]})
    again = {i["muscle"]: i["exercise"] for i in build_plan(conn, NOW, CHEST)["items"] if i["kind"] == "add"}
    assert again.get("rear_delt") not in (None, first["rear_delt"])


def test_comeback_holds_weights(conn):
    add_gym(conn, NOW - timedelta(days=12), [(BENCH, 80, 12, "normal")] * 3 + [(OHP, 40, 10, "normal")] * 3, title="A")
    plan = build_plan(conn, NOW, "A")
    assert plan["comeback"] is True
    bench = items_by(plan)[BENCH]
    assert (bench["change"], bench["weight_kg"]) == ("welcome_back", 80)
    assert all(i["kind"] == "routine" for i in plan["items"])
    with pytest.raises(ValueError, match="comeback"):
        build_plan(conn, NOW, None)


def test_missed_plan(conn):
    chest_day(conn, day(20))
    conn.execute(text("update profile set avoid_muscles = '{lower_back}'"))
    plan = build_plan(conn, NOW, None)
    assert 1 <= len(plan["items"]) <= 5 and plan["day"] is None
    assert all(i["kind"] == "missed" and i["suggested"] for i in plan["items"])
    assert "lower_back" not in {i["muscle"] for i in plan["items"]}


def test_swap_item_cycles_alternatives(conn):
    chest_day(conn, day(20))
    plan = build_plan(conn, NOW, CHEST)
    add = next(i for i in plan["items"] if i["kind"] == "add" and i["muscle"] == "rear_delt")
    once = swap_item(conn, NOW, plan, add["id"])
    first = next(i for i in once["items"] if i["id"] == add["id"])
    twice = swap_item(conn, NOW, once, add["id"])
    second = next(i for i in twice["items"] if i["id"] == add["id"])
    assert len({add["exercise"], first["exercise"], second["exercise"]}) == 3
    assert first["muscle"] == second["muscle"] == "rear_delt"


def test_goal_matching():
    bench = {"text": "Bench 100 kg", "exercise": None, "status": "active", "target": "by March"}
    assert goal_for(BENCH, [bench]) == bench
    assert goal_for(INCLINE, [bench]) is None
    assert goal_for("Cable Fly Crossover", [{"text": "Get better at cable stuff", "exercise": None, "status": "active"}]) is None
    explicit = {"text": "Pressing strength", "exercise": OHP, "status": "active"}
    assert goal_for(OHP, [explicit]) == explicit
    assert goal_for(BENCH, [dict(bench, status="achieved")]) is None


def test_no_gym_history(conn):
    assert routines(conn, NOW) == []


def test_swapping_the_variety_pick_never_mislabels_the_stuck_lift(conn):
    _stalled_ohp(conn)
    plan = build_plan(conn, NOW, CHEST)
    variety = next(i for i in plan["items"] if i["kind"] == "swap")
    seen = []
    for _ in range(4):
        try:
            plan = swap_item(conn, NOW, plan, variety["id"])
        except LookupError:
            break
        item = next(i for i in plan["items"] if i["id"] == variety["id"])
        seen.append(item["exercise"])
        if item["exercise"] == OHP:  # back to the owner's own lift: shown as their routine, with last time's sets
            assert item["kind"] == "routine" and item["replaces"] is None and item["last"] and item["change"] == "same"
            break
        assert item["kind"] == "swap" and item["replaces"] == OHP
    assert seen and len(seen) == len(set(seen))


def test_dose_targets_the_sets_at_the_top_weight(conn):
    add_gym(conn, day(24), [(BENCH, 50, 13, "normal"), (BENCH, 70, 10, "normal"), (BENCH, 80, 6, "normal"),
                            (BENCH, 80, 5, "normal")], title="A")
    bench = items_by(build_plan(conn, NOW, "A"))[BENCH]
    assert (bench["sets"], bench["reps"], bench["weight_kg"], bench["change"]) == (2, "6", 80, "same")
    assert bench["lighter_sets"] == 2


def test_progression_uses_the_latest_session_of_that_exercise(conn):
    add_gym(conn, day(20), [(BENCH, 60, 8, "normal")] * 3 + [(OHP, 40, 10, "normal")] * 3, title=CHEST)
    add_gym(conn, day(24), [(BENCH, 60, 12, "normal")] * 3, title="General")
    bench = items_by(build_plan(conn, NOW, CHEST))[BENCH]
    assert (bench["change"], bench["weight_kg"]) == ("up", 62.5)
    assert bench["last"] == [{"kg": 60, "reps": 12}] * 3


def test_empty_sets_are_ignored(conn):
    ext = "Triceps Extension (Cable)"
    add_gym(conn, day(24), [(ext, 12.5, 10, "normal"), (ext, 12.5, 6, "normal"), (ext, 12.5, 0, "normal")], title="A")
    item = items_by(build_plan(conn, NOW, "A"))[ext]
    assert (item["sets"], item["reps"], item["weight_kg"]) == (2, "7", 12.5)
