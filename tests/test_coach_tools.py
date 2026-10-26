import json
from datetime import UTC, datetime

from sqlalchemy import text

from lockedin.coach.tools import TOOLS, execute_tool

NOW = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)


def run(conn, engine, name, args):
    return execute_tool(name, args, conn=conn, engine=engine, now=NOW)


def test_tool_definitions_are_strict_and_stream_eagerly():
    names = {t["name"] for t in TOOLS}
    assert names == {"get_schema", "run_sql", "get_focus_facts", "get_goals", "save_goal", "mark_goals_reviewed",
                     "get_agenda", "save_agenda"}
    for t in TOOLS:
        assert t["eager_input_streaming"] is True
        assert t["input_schema"]["additionalProperties"] is False


def test_schema_describes_the_readable_tables(clean_db):
    with clean_db.begin() as c:
        out, err = run(c, clean_db, "get_schema", {})
    assert not err
    for table in ["activities", "gym_sets", "measurements", "goals", "profile"]:
        assert table in out
    assert "fit_files" not in out


def test_get_goals_empty(clean_db):
    with clean_db.begin() as c:
        assert run(c, clean_db, "get_goals", {}) == ("[]", False)


def test_save_goal_lifecycle(clean_db):
    with clean_db.begin() as c:
        out, err = run(c, clean_db, "save_goal", {"action": "create", "text": "Bench 100 kg", "area": "gym",
                                                  "target": "by March 2027"})
        assert not err
        goal = json.loads(out)
        assert goal["text"] == "Bench 100 kg" and goal["status"] == "active" and goal["source"] == "coach"
        assert c.execute(text("select last_goal_review_at from profile")).scalar() == NOW

        out, err = run(c, clean_db, "save_goal", {"action": "update", "goal_id": goal["id"], "target": "by April 2027"})
        assert not err and json.loads(out)["target"] == "by April 2027" and json.loads(out)["text"] == "Bench 100 kg"

        out, err = run(c, clean_db, "save_goal", {"action": "achieved", "goal_id": goal["id"]})
        assert not err and json.loads(out)["status"] == "achieved"
        assert json.loads(run(c, clean_db, "get_goals", {})[0])[0]["status"] == "achieved"


def test_save_goal_rejects_bad_input(clean_db):
    with clean_db.begin() as c:
        for args in [{"action": "create"}, {"action": "create", "text": "  "}, {"action": "dropped", "goal_id": 99},
                     {"action": "update"}, {"action": "explode", "goal_id": 1},
                     {"action": "create", "text": "x", "colour": "red"}, "not an object"]:
            out, err = run(c, clean_db, "save_goal", args)
            assert err, args
        assert c.execute(text("select count(*) from goals")).scalar() == 0


def test_mark_goals_reviewed(clean_db):
    with clean_db.begin() as c:
        assert run(c, clean_db, "mark_goals_reviewed", {}) == ("ok", False)
        assert c.execute(text("select last_goal_review_at from profile")).scalar() == NOW


def test_run_sql_tool(clean_db):
    with clean_db.begin() as c:
        out, err = run(c, clean_db, "run_sql", {"query": "select 2 + 2 as four"})
        assert not err and json.loads(out)["rows"] == [[4]]
        out, err = run(c, clean_db, "run_sql", {"query": "delete from goals"})
        assert err and "select" in out.lower()
        assert run(c, clean_db, "run_sql", {"query": 5})[1] is True
        assert run(c, clean_db, "run_sql", {})[1] is True


def test_focus_facts_tool(clean_db):
    with clean_db.begin() as c:
        out, err = run(c, clean_db, "get_focus_facts", {})
    assert not err and "coverage" in json.loads(out)


def test_unknown_tool(clean_db):
    with clean_db.begin() as c:
        out, err = run(c, clean_db, "drop_everything", {})
    assert err and "drop_everything" in out
