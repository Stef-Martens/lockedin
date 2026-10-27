import json
from datetime import UTC, datetime

from focus_helpers import add_gym
from sqlalchemy import text
from test_run_steps import TEMPO

from lockedin.coach.prompt import turn_context
from lockedin.coach.tools import AGENDA_CHANGE, TOOLS, execute_tool

NOW = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)  # Monday
SWEET_SPOT = {"blocks": [
    {"type": "warmup", "duration_s": 600, "from_power": 0.5, "to_power": 0.75},
    {"type": "intervals", "repeat": 3, "on_s": 600, "off_s": 300, "on_power": 0.9, "off_power": 0.55},
    {"type": "cooldown", "duration_s": 600, "from_power": 0.65, "to_power": 0.45},
]}


def run(engine, name, args):
    with engine.begin() as c:
        return execute_tool(name, args, conn=c, engine=engine, now=NOW)


def count(engine):
    with engine.begin() as c:
        return c.execute(text("select count(*) from agenda_items")).scalar()


def test_agenda_tools_are_declared():
    names = {t["name"] for t in TOOLS}
    assert {"get_agenda", "save_agenda"} <= names


def test_save_agenda_adds_moves_and_deletes(clean_db):
    with clean_db.begin() as c:
        add_gym(c, datetime(2026, 10, 21, 17, tzinfo=UTC), [("Lat Pulldown (Cable)", 60, 10, "normal")], title="Rug - Bicep")
    out, err = run(clean_db, "save_agenda", {"changes": [
        {"op": "add", "day": "2026-10-27", "sport": "gym", "title": "Rug - Bicep", "routine": "Rug - Bicep"},
        {"op": "add", "day": "2026-10-29", "sport": "bike", "title": "Sweet Spot 3x10", "zwift": SWEET_SPOT},
        {"op": "add", "day": "2026-10-31", "sport": "rest", "title": "Rest", "optional": False},
    ]})
    assert not err, out
    added = json.loads(out)
    assert [a["op"] for a in added] == ["added"] * 3 and all(a["source"] == "coach" for a in added)
    ride = added[1]
    out, err = run(clean_db, "save_agenda", {"changes": [{"op": "update", "id": ride["id"], "day": "2026-10-30"},
                                                         {"op": "delete", "id": added[2]["id"]}]})
    assert not err, out
    agenda = json.loads(run(clean_db, "get_agenda", {})[0])
    assert {(i["title"], i["day"]) for i in agenda} == {("Rug - Bicep", "2026-10-27"), ("Sweet Spot 3x10", "2026-10-30")}
    assert all("done" in i for i in agenda)


def test_save_agenda_is_all_or_nothing(clean_db):
    bad = dict(SWEET_SPOT, blocks=[{"type": "steady", "duration_s": 600, "power": 5}])
    out, err = run(clean_db, "save_agenda", {"changes": [
        {"op": "add", "day": "2026-10-28", "sport": "run", "title": "Easy run"},
        {"op": "add", "day": "2026-10-29", "sport": "bike", "title": "Too hard", "zwift": bad},
    ]})
    assert err and "Change 2" in out
    assert count(clean_db) == 0


def test_unknown_routine_names_the_real_ones(clean_db):
    with clean_db.begin() as c:
        add_gym(c, datetime(2026, 10, 21, 17, tzinfo=UTC), [("Lat Pulldown (Cable)", 60, 10, "normal")], title="Rug - Bicep")
    out, err = run(clean_db, "save_agenda", {"changes": [
        {"op": "add", "day": "2026-10-27", "sport": "gym", "title": "Back", "routine": "Back day"}]})
    assert err and "Rug - Bicep" in out


def test_save_agenda_rejects_garbage(clean_db):
    for args in [{}, {"changes": "everything"}, {"changes": [{"op": "explode"}]}, {"changes": [{"op": "update", "id": 999}]},
                 {"changes": [{"op": "add", "day": "someday", "sport": "run", "title": "x"}]}]:
        out, err = run(clean_db, "save_agenda", args)
        assert err, args
    assert count(clean_db) == 0


def test_turn_context_mentions_todays_plan(clean_db):
    run(clean_db, "save_agenda", {"changes": [
        {"op": "add", "day": "2026-10-26", "sport": "bike", "title": "Recovery Spin 30", "optional": True},
        {"op": "add", "day": "2026-10-27", "sport": "run", "title": "Easy run"}]})
    with clean_db.begin() as c:
        ctx = turn_context(c, NOW)
    assert "Recovery Spin 30" in ctx and "Easy run" in ctx


def test_prompt_asks_for_optional_sessions_as_their_own_item():
    from lockedin.coach.prompt import SYSTEM_PROMPT
    assert "own item with optional: true" in SYSTEM_PROMPT


def test_agenda_tool_schema_has_steps():
    targets = AGENDA_CHANGE["properties"]["targets"]["properties"]
    steps = targets["steps"]["properties"]
    block_step = steps["blocks"]["items"]["properties"]["steps"]["items"]["properties"]
    assert block_step["kind"]["enum"] == ["work", "recovery"]
    assert {"time_s", "distance_m", "open"} <= set(block_step["goal"]["properties"])
    assert {"warmup", "cooldown"} <= set(steps)


def test_coach_saves_run_with_steps(clean_db):
    out, err = run(clean_db, "save_agenda", {"changes": [
        {"op": "add", "day": "2026-10-28", "sport": "run", "title": "Tempo 4x5", "targets": {"steps": TEMPO}}]})
    assert not err, out
    added = json.loads(out)[0]
    assert added["plan_line"] == "10′ warm-up Z2 · 4 × (5′ @ 5:30–5:50, 2′ jog) · cool-down"
    item = json.loads(run(clean_db, "get_agenda", {})[0])[0]
    assert item["targets"]["steps"]["blocks"][0]["repeat"] == 4 and item["plan_line"] == added["plan_line"]


def test_coach_bad_steps_message(clean_db):
    steps = {"blocks": [{"repeat": 1, "steps": [{"kind": "work", "goal": {"time_s": 300, "distance_m": 1000}}]}]}
    out, err = run(clean_db, "save_agenda", {"changes": [
        {"op": "add", "day": "2026-10-28", "sport": "run", "title": "Bad", "targets": {"steps": steps}}]})
    assert err and "exactly one of time_s, distance_m or open" in out
    assert count(clean_db) == 0


def test_prompt_mentions_steps():
    from lockedin.coach.prompt import SYSTEM_PROMPT
    assert '"steps": null' in SYSTEM_PROMPT and "work out the summary" in SYSTEM_PROMPT
