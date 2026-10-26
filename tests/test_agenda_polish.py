from datetime import UTC, date, datetime

from conftest import owner_headers
from sqlalchemy import text

from lockedin.agenda.zwo import ZwiftWorkout, filename, render
from lockedin.app import app
from lockedin.coach import prompt
from lockedin.coach.prompt import turn_context
from lockedin.coach.tools import execute_tool
from lockedin.routes.overview import get_now

NOW = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)
H = owner_headers()
RIDE = {"blocks": [{"type": "steady", "duration_s": 1800, "power": 0.6}]}


def post(client, **body):
    app.dependency_overrides[get_now] = lambda: NOW
    return client.post("/api/agenda", headers=H, json=body)


def test_422_message_has_no_pydantic_prefix(client, clean_db):
    r = post(client, day="2026-10-28", sport="run", title="   ")
    assert r.status_code == 422
    msgs = [d["msg"] for d in r.json()["detail"]]
    assert msgs == ["Give it a title."]


def test_control_characters_are_stripped(client, clean_db):
    r = post(client, day="2026-10-28", sport="bike", title="Sweet\x07 Spot", note="line one\nline\ttwo\x00", zwift=RIDE)
    assert r.status_code == 201, r.text
    item = r.json()
    assert item["title"] == "Sweet Spot" and item["note"] == "line one\nline\ttwo"
    iid = item["id"]
    r = client.patch(f"/api/agenda/{iid}", headers=H, json={"title": "Easy\x1b spin"})
    assert r.json()["title"] == "Easy spin"


def test_zwo_with_odd_characters_still_parses():
    import xml.etree.ElementTree as ET
    ET.fromstring(render("Ride\x07", date(2026, 10, 28), "note\x0b", ZwiftWorkout(**RIDE)))


def test_file_names_keep_accented_letters_readable():
    assert filename("Vélo endurance", date(2026, 10, 28)) == "2026-10-28 Velo endurance.zwo"


def _save(engine, changes):
    with engine.begin() as c:
        return execute_tool("save_agenda", {"changes": changes}, conn=c, engine=engine, now=NOW)


def test_save_agenda_caps_changes_server_side(clean_db, monkeypatch):
    from lockedin.coach import tools
    monkeypatch.setitem(tools.SCHEMAS["save_agenda"]["properties"]["changes"], "maxItems", 1000)
    out, err = _save(clean_db, [{"op": "add", "day": "2026-10-28", "sport": "run", "title": f"Run {n}"} for n in range(31)])
    assert err and "30" in out


def test_save_agenda_rejects_a_boolean_id(clean_db):
    _save(clean_db, [{"op": "add", "day": "2026-10-28", "sport": "run", "title": "Run"}])
    out, err = _save(clean_db, [{"op": "delete", "id": True}])
    assert err and "id" in out
    with clean_db.begin() as c:
        assert c.execute(text("select count(*) from agenda_items")).scalar() == 1


def test_turn_context_survives_an_agenda_failure(clean_db, monkeypatch):
    def broken(*a, **k):
        raise RuntimeError("boom")
    monkeypatch.setattr(prompt, "items_between", broken)
    with clean_db.begin() as c:
        ctx = turn_context(c, NOW)
    assert "Agenda: unavailable right now." in ctx
