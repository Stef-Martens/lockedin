import json
from datetime import UTC, date, datetime

from sqlalchemy import text

from lockedin import timeoff
from lockedin.coach.prompt import SYSTEM_PROMPT, turn_context
from lockedin.coach.tools import SCHEMA_TEXT, TOOLS, execute_tool

NOW = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)
KNEE = {"reason": "injury", "label": "Knee operation", "start": "2026-12-03",
        "restrictions": [{"category": "run", "until": "2026-12-17"}, {"category": "upper", "until": "2027-01-02"}]}


def run(engine, args):
    with engine.begin() as c:
        return execute_tool("save_time_off", args, conn=c, engine=engine, now=NOW)


def stored(engine):
    with engine.begin() as c:
        return timeoff.entries(c)


def test_tool_is_declared_and_documented():
    tool = next(t for t in TOOLS if t["name"] == "save_time_off")
    assert "clearly agreed" in tool["description"]
    assert tool["input_schema"]["required"] == ["action"]
    assert "time_off:" in SCHEMA_TEXT


def test_create_update_delete(clean_db):
    out, err = run(clean_db, {"action": "create", "entry": KNEE})
    assert not err
    saved = json.loads(out)
    assert saved["label"] == "Knee operation" and saved["end"] == "2027-01-02"
    assert [e["id"] for e in stored(clean_db)] == [saved["id"]]

    shorter = {**KNEE, "restrictions": [{"category": "run", "until": "2026-12-10"}]}
    out, err = run(clean_db, {"action": "update", "id": saved["id"], "entry": shorter})
    assert not err and json.loads(out)["end"] == "2026-12-10"
    assert stored(clean_db)[0]["end"] == date(2026, 12, 10)

    out, err = run(clean_db, {"action": "delete", "id": saved["id"]})
    assert not err and json.loads(out) == {"deleted": saved["id"]}
    assert stored(clean_db) == []


def test_bad_input_is_a_plain_error_and_stores_nothing(clean_db):
    clash = {**KNEE, "restrictions": [{"category": "run", "until": "2026-12-17"}, {"category": "run", "until": "2026-12-20"}]}
    early = {**KNEE, "restrictions": [{"category": "run", "until": "2026-12-01"}]}
    for args in [{"action": "create"}, {"action": "create", "entry": clash}, {"action": "create", "entry": early},
                 {"action": "create", "entry": {**KNEE, "reason": "holiday"}},
                 {"action": "create", "entry": {**KNEE, "restrictions": []}},
                 {"action": "update", "entry": KNEE}, {"action": "update", "id": 99, "entry": KNEE},
                 {"action": "delete"}, {"action": "delete", "id": 99}, {"action": "explode"},
                 {"action": "create", "entry": KNEE, "colour": "red"}]:
        out, err = run(clean_db, args)
        assert err and out and "Value error" not in out and "Traceback" not in out, args
    assert stored(clean_db) == []


def test_context_lists_current_and_upcoming_time_off(clean_db):
    run(clean_db, {"action": "create", "entry": KNEE})
    run(clean_db, {"action": "create", "entry": {
        "reason": "vacation", "start": "2026-08-01", "restrictions": [{"category": "all", "until": "2026-08-10"}]}})
    with clean_db.begin() as c:
        ctx = turn_context(c, NOW)
    assert "Time off: Knee operation from 3 Dec: no running until 17 Dec, no upper body until 2 Jan" in ctx
    assert "1 Aug" not in ctx  # over, and long enough ago that nothing is easy any more
    assert "Back from time off" not in ctx

    with clean_db.begin() as c:
        c.execute(text("delete from time_off"))
        assert "Time off" not in turn_context(c, NOW)


def test_context_names_an_unlabelled_entry_by_its_reason(clean_db):
    run(clean_db, {"action": "create", "entry": {
        "reason": "vacation", "start": "2026-10-20", "restrictions": [{"category": "all", "until": "2026-10-30"}]}})
    with clean_db.begin() as c:
        assert "Time off: Vacation from 20 Oct: everything off until 30 Oct" in turn_context(c, NOW)


def test_prompt_covers_agreement_dates_planning_and_no_medical_advice():
    for phrase in ["Save?", "surgeon or physio", "save_time_off", "start + 14 days", "next month", "75% FTP", "everything-off", "Back from time off",
                   "first two weeks back after your operation"]:
        assert phrase in SYSTEM_PROMPT, phrase


def test_context_says_when_a_sport_is_back_and_should_stay_easy(clean_db):
    run(clean_db, {"action": "create", "entry": {**KNEE, "start": "2026-10-01", "restrictions": [
        {"category": "run", "until": "2026-10-20"}, {"category": "upper", "until": "2026-10-20"}]}})

    def ctx_on(day):
        with clean_db.begin() as c:
            return turn_context(c, datetime.fromisoformat(f"{day}T12:00:00+00:00"))

    line = ("Back from time off: running allowed again since 21 Oct \u2014 plan it easy until 3 Nov "
            "(first two weeks back after Knee operation).")
    assert line in ctx_on("2026-10-21") and line in ctx_on("2026-11-03")
    assert "Back from time off" not in ctx_on("2026-11-04")
    assert "Back from time off" not in ctx_on("2026-10-20")  # still off on its last day
    assert "swimming allowed" not in ctx_on("2026-10-21") and "upper body allowed" not in ctx_on("2026-10-21")

    run(clean_db, {"action": "create", "entry": {  # off again
        "reason": "vacation", "start": "2026-10-25", "restrictions": [{"category": "run", "until": "2026-10-30"}]}})
    assert "Back from time off" not in ctx_on("2026-10-26")


def test_context_says_when_everything_is_back(clean_db):
    run(clean_db, {"action": "create", "entry": {
        "reason": "vacation", "label": "Ski trip", "start": "2026-10-10", "restrictions": [{"category": "all", "until": "2026-10-20"}]}})
    with clean_db.begin() as c:
        ctx = turn_context(c, NOW)
    for sport in ("running", "cycling", "swimming"):
        assert f"{sport} allowed again since 21 Oct" in ctx
    assert "first two weeks back after Ski trip" in ctx
