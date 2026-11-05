import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from conftest import SYNC_HEADERS, WATCH_HEADERS, owner_headers
from focus_helpers import add_session
from sqlalchemy import text
from test_coach_loop import FakeLLM, text_block

from lockedin.app import app
from lockedin.coach.llm import Final
from lockedin.config import get_settings
from lockedin.routes import coach, verdicts
from lockedin.routes.overview import get_now
from lockedin.verdict import store

NOW = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)
START = datetime(2026, 11, 3, 17, 0, tzinfo=UTC)
H = owner_headers()
USAGE = [{"model": "claude-opus-5-5", "input_tokens": 1000, "output_tokens": 200}]


def good(label="on_plan", body="Steady run."):
    return ([], [text_block(json.dumps({"label": label, "text": body}))], "end_turn")


class Fake(FakeLLM):
    """FakeLLM whose answers are billed, and that can do something while the model is 'thinking'."""

    during = None

    def stream(self, *, system, messages, tools, tool_choice=None, output_format=None):
        if self.during:
            self.during()
        for event in super().stream(system=system, messages=messages, tools=tools, tool_choice=tool_choice,
                                    output_format=output_format):
            yield Final(event.content, event.stop_reason, USAGE) if isinstance(event, Final) else event


@pytest.fixture
def fake(client, clean_db):
    llm = Fake([])
    app.dependency_overrides[verdicts.get_verdict_llm] = lambda: lambda: llm
    app.dependency_overrides[coach.get_coach_engine] = lambda: clean_db
    app.dependency_overrides[get_now] = lambda: NOW
    return llm


@pytest.fixture
def run(clean_db):
    with clean_db.begin() as c:
        return add_session(c, "run", START, 1800, distance_m=5000, avg_hr=150)


def item(db, sport="run", title="Tempo", day="2026-11-03") -> int:
    with db.begin() as c:
        return c.execute(text("insert into agenda_items (day, sport, title) values (:d, :s, :t) returning id"),
                         {"d": day, "s": sport, "t": title}).scalar_one()


def get(client, path="latest"):
    return client.get(f"/api/verdicts/{path}", headers=H)


def row(db, aid):
    with db.begin() as c:
        return c.execute(text("select * from workout_verdicts where activity_id = :a"), {"a": aid}).first()


def test_writes_once_then_serves_saved(client, fake, run, clean_db):
    fake.turns = [good(body="Steady run.")]
    first = get(client).json()
    assert first["verdict"] == {"status": "done", "label": "unplanned", "text": "Steady run."}
    assert first["activity"] == {"id": run, "sport": "run", "day": "2026-11-03", "start_at": "2026-11-03T17:00:00Z",
                                 "title": None, "item_id": None}
    assert get(client).json() == first
    assert get(client, str(run)).json() == first
    assert len(fake.calls) == 1
    assert row(clean_db, run).model == get_settings().anthropic_model


def test_planned_workout_uses_title_and_models_label(client, fake, run, clean_db):
    i = item(clean_db)
    fake.turns = [good("close", "Mostly there.")]
    r = get(client).json()
    assert r["activity"]["title"] == "Tempo" and r["activity"]["item_id"] == i
    assert r["verdict"] == {"status": "done", "label": "close", "text": "Mostly there."}


def test_concurrent_second_request_sees_writing(client, fake, run):
    fake.turns = [good()]
    seen = []
    fake.during = lambda: seen.append(get(client).json()["verdict"])
    assert get(client).json()["verdict"]["status"] == "done"
    assert seen == [{"status": "writing"}] and len(fake.calls) == 1


def test_records_usage_without_a_conversation(client, fake, run, clean_db):
    fake.turns = [good()]
    get(client)
    with clean_db.begin() as c:
        rows = c.execute(text("select conversation_id, model, input_tokens, output_tokens from coach.usage")).all()
    assert [tuple(r) for r in rows] == [(None, "claude-opus-5-5", 1000, 200)]


def test_usage_failure_keeps_the_verdict(client, fake, run, clean_db, monkeypatch):
    fake.turns = [good()]

    def boom(*a, **k):
        raise RuntimeError("no usage table")

    monkeypatch.setattr(verdicts.usage, "record", boom)
    assert get(client).json()["verdict"]["status"] == "done"
    assert row(clean_db, run).label == "unplanned"


def test_over_budget(client, fake, run, clean_db):
    with clean_db.begin() as c:
        c.execute(text("insert into coach.usage (model, cost_usd, created_at) values ('m', 99, :n)"), {"n": NOW})
    assert get(client).json()["verdict"] == {"status": "over_budget"}
    assert fake.calls == [] and row(clean_db, run) is None


def test_no_key_is_none(client, fake, run, clean_db):
    app.dependency_overrides[verdicts.get_verdict_llm] = lambda: None
    assert get(client).json()["verdict"] == {"status": "none"}
    assert row(clean_db, run) is None


def test_real_dependency_is_none_without_a_key():
    assert verdicts.get_verdict_llm(replace(get_settings(), anthropic_api_key=None)) is None


def test_old_workout_is_no_card(client, fake, clean_db):
    with clean_db.begin() as c:
        add_session(c, "run", NOW - timedelta(days=15), 1800)
    assert get(client).json() == {"activity": None}


def test_no_workouts_is_no_card_and_404(client, fake):
    assert get(client).json() == {"activity": None}
    assert get(client, "5").status_code == 404


def test_old_workout_page_is_none(client, fake, clean_db):
    with clean_db.begin() as c:
        old = add_session(c, "run", NOW - timedelta(days=15), 1800)
    r = get(client, str(old)).json()
    assert r["verdict"] == {"status": "none"} and r["activity"]["id"] == old
    assert fake.calls == []


def test_old_saved_is_still_shown(client, fake, clean_db):
    with clean_db.begin() as c:
        old = add_session(c, "run", NOW - timedelta(days=15), 1800)
    fake.turns = [good()]
    # written while it was new, then it aged
    app.dependency_overrides[get_now] = lambda: NOW - timedelta(days=10)
    assert get(client, str(old)).json()["verdict"]["status"] == "done"
    app.dependency_overrides[get_now] = lambda: NOW
    with clean_db.begin() as c:
        i = c.execute(text("insert into agenda_items (day, sport, title) values (:d, 'run', 'x') returning id"),
                      {"d": (NOW - timedelta(days=15)).date()}).scalar_one()
    r = get(client, str(old)).json()
    assert r["verdict"]["status"] == "done" and r["activity"]["item_id"] == i and len(fake.calls) == 1


def test_failure_is_failed_and_waits(client, fake, run, clean_db):
    fake.turns = [RuntimeError("boom")]
    assert get(client).json()["verdict"] == {"status": "failed"}
    assert get(client).json()["verdict"] == {"status": "failed"}
    assert len(fake.calls) == 1
    assert row(clean_db, run).written_at is None
    app.dependency_overrides[get_now] = lambda: NOW + timedelta(minutes=16)
    fake.turns = [good()]
    assert get(client).json()["verdict"]["status"] == "done" and len(fake.calls) == 2


def test_refused_answer_is_failed_but_billed(client, fake, run, clean_db):
    fake.turns = [([], [text_block("not json")], "end_turn")]
    assert get(client).json()["verdict"] == {"status": "failed"}
    with clean_db.begin() as c:
        assert c.execute(text("select count(*) from coach.usage")).scalar() == 1


def test_claim_left_behind_shows_writing_then_is_taken_over(client, fake, run, clean_db):
    with clean_db.begin() as c:
        c.execute(text("insert into workout_verdicts (activity_id, claimed_at) values (:a, :n)"), {"a": run, "n": NOW})
    assert get(client).json()["verdict"] == {"status": "writing"}
    app.dependency_overrides[get_now] = lambda: NOW + timedelta(minutes=7)
    fake.turns = [good()]
    assert get(client).json()["verdict"]["status"] == "done"


def later():
    """Past the claim's 6 minutes: a verdict can't be rewritten right after it was written."""
    app.dependency_overrides[get_now] = lambda: NOW + timedelta(minutes=7)


def written_unplanned(client, fake):
    fake.turns = [good(), good("on_plan", "Rewritten.")]
    assert get(client).json()["verdict"]["label"] == "unplanned"


def test_plan_added_later_rewrites(client, fake, run, clean_db):
    written_unplanned(client, fake)
    item(clean_db)
    later()
    r = get(client).json()
    assert r["verdict"] == {"status": "done", "label": "on_plan", "text": "Rewritten."} and len(fake.calls) == 2
    assert get(client).json() == r and len(fake.calls) == 2


def test_item_deleted_rewrites(client, fake, run, clean_db):
    i = item(clean_db)
    fake.turns = [good(), good()]
    assert get(client).json()["verdict"]["label"] == "on_plan"
    with clean_db.begin() as c:
        c.execute(text("delete from agenda_items where id = :i"), {"i": i})
    later()
    assert get(client).json()["verdict"]["label"] == "unplanned" and len(fake.calls) == 2


def test_target_edit_does_not_rewrite(client, fake, run, clean_db):
    i = item(clean_db)
    fake.turns = [good()]
    get(client)
    with clean_db.begin() as c:
        c.execute(text("update agenda_items set title = 'Harder', targets = '{\"distance_m\": 9000}' where id = :i"),
                  {"i": i})
    assert get(client).json()["verdict"]["status"] == "done" and len(fake.calls) == 1


def test_second_workout_swap_does_not_rewrite(client, fake, run, clean_db):
    first = item(clean_db, title="Tempo")
    second = item(clean_db, title="Easy")
    fake.turns = [good()]
    assert get(client).json()["activity"]["item_id"] == first
    with clean_db.begin() as c:  # an earlier run the same day takes the first item; this one moves to the second
        add_session(c, "run", START - timedelta(hours=8), 3600)
    later()
    r = get(client, str(run)).json()
    assert r["activity"]["item_id"] == second and r["verdict"]["status"] == "done" and len(fake.calls) == 1


def test_rest_day_is_unplanned(client, fake, run, clean_db):
    i = item(clean_db, sport="rest", title="Rest")
    fake.turns = [good("on_plan", "You rested, then ran.")]
    r = get(client).json()
    assert r["verdict"]["label"] == "unplanned" and r["activity"]["item_id"] == i and r["activity"]["title"] == "Rest"
    assert get(client).json()["verdict"]["status"] == "done" and len(fake.calls) == 1


def test_superseded_is_404(client, fake, clean_db):
    with clean_db.begin() as c:
        real = add_session(c, "run", START, 1800)
        dup = add_session(c, "run", START, 1800, superseded_by=real)
    assert get(client, str(dup)).status_code == 404


@pytest.mark.parametrize("path", ["latest", "1"])
def test_requires_owner(client, path):
    assert client.get(f"/api/verdicts/{path}").status_code == 401
    assert client.get(f"/api/verdicts/{path}", headers=SYNC_HEADERS).status_code == 401
    assert client.get(f"/api/verdicts/{path}", headers=WATCH_HEADERS).status_code == 401


def test_no_store(client, fake, run):
    fake.turns = [good()]
    assert get(client).headers["cache-control"] == "no-store"
    assert get(client, str(run)).headers["cache-control"] == "no-store"


def test_real_dependency_builds_no_client_until_asked(monkeypatch):
    built = []
    monkeypatch.setattr(verdicts, "AnthropicLLM", lambda key, model: built.append((key, model)) or "llm")
    make = verdicts.get_verdict_llm(replace(get_settings(), anthropic_api_key="sk-x", anthropic_model="m"))
    assert built == []
    assert make() == "llm" and built == [("sk-x", "m")]


def test_saved_verdict_and_waiting_do_not_build_a_client(client, fake, run, clean_db):
    fake.turns = [good()]
    made = []
    app.dependency_overrides[verdicts.get_verdict_llm] = lambda: lambda: made.append(1) or fake
    assert get(client).json()["verdict"]["status"] == "done"
    assert made == [1]
    assert get(client).json()["verdict"]["status"] == "done"
    assert made == [1]  # served from the saved row


def test_a_claim_held_elsewhere_builds_no_client(client, fake, run, clean_db):
    with clean_db.begin() as c:
        store.claim(c, run, None, NOW, rewrite=False)
    made = []
    app.dependency_overrides[verdicts.get_verdict_llm] = lambda: lambda: made.append(1) or fake
    assert get(client).json()["verdict"] == {"status": "writing"}
    assert made == []


def test_an_unplanned_ride_has_no_title_to_repeat(client, fake, clean_db):
    with clean_db.begin() as c:
        add_session(c, "bike", START, 3600, distance_m=30000, avg_hr=140)
    fake.turns = [good()]
    a = get(client).json()["activity"]
    assert a["sport"] == "bike" and a["title"] is None
