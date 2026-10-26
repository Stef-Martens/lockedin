import json
from dataclasses import replace

import pytest
from conftest import owner_headers
from sqlalchemy import text
from test_coach_loop import FakeLLM, answer, text_block, tool_use

from lockedin.app import app
from lockedin.config import get_settings
from lockedin.routes import coach


@pytest.fixture
def fake(client, clean_db):
    llm = FakeLLM([])
    app.dependency_overrides[coach.get_llm] = lambda: llm
    app.dependency_overrides[coach.get_coach_engine] = lambda: clean_db
    return llm


def events(response) -> list[dict]:
    assert response.headers["content-type"].startswith("text/event-stream")
    return [json.loads(chunk[len("data: "):]) for chunk in response.text.split("\n\n") if chunk.startswith("data: ")]


def new_conversation(client) -> int:
    r = client.post("/api/coach/conversations", headers=owner_headers())
    assert r.status_code == 201
    return r.json()["id"]


def send(client, cid, msg="What should I focus on this week?"):
    return client.post(f"/api/coach/conversations/{cid}/messages", json={"text": msg}, headers=owner_headers())


def test_message_streams_and_is_stored(client, fake, clean_db):
    fake.turns = [(["Focus on ", "triceps."], [text_block("Focus on triceps.")], "end_turn")]
    cid = new_conversation(client)
    r = send(client, cid)
    assert r.status_code == 200
    assert events(r) == [{"type": "text", "text": "Focus on "}, {"type": "text", "text": "triceps."}, {"type": "done"}]
    with clean_db.begin() as c:
        rows = c.execute(text("select role, content from coach_messages where conversation_id = :c order by id"),
                         {"c": cid}).all()
    assert [r.role for r in rows] == ["user", "system", "assistant"]
    assert rows[0].content == "What should I focus on this week?" and "Brussels" in rows[1].content

    convo = client.get(f"/api/coach/conversations/{cid}", headers=owner_headers()).json()
    assert convo["title"] == "What should I focus on this week?"
    assert convo["messages"] == [{"role": "user", "text": "What should I focus on this week?", "tools": []},
                                 {"role": "assistant", "text": "Focus on triceps.", "tools": []}]


def test_tool_rounds_show_as_one_answer_and_goals_get_saved(client, fake):
    fake.turns = [
        (["Let me check."], [text_block("Let me check."), tool_use(1, "get_goals")], "tool_use"),
        ([], [tool_use(2, "save_goal", {"action": "create", "text": "Bench 100 kg"})], "tool_use"),
        answer("Saved your goal."),
    ]
    cid = new_conversation(client)
    evs = events(send(client, cid, "Yes, save bench 100 kg as a goal"))
    assert {"type": "tool", "name": "save_goal", "status": "done"} in evs and evs[-1] == {"type": "done"}
    convo = client.get(f"/api/coach/conversations/{cid}", headers=owner_headers()).json()
    assert convo["messages"][1] == {"role": "assistant", "text": "Let me check.\n\nSaved your goal.",
                                    "tools": ["get_goals", "save_goal"]}
    goals = client.get("/api/coach/goals", headers=owner_headers()).json()
    assert [g["text"] for g in goals] == ["Bench 100 kg"]


def test_second_message_replays_history_unchanged(client, fake):
    fake.turns = [answer("First."), answer("Second.")]
    cid = new_conversation(client)
    send(client, cid, "one")
    send(client, cid, "two")
    first, second = fake.calls[0]["messages"], fake.calls[1]["messages"]
    assert second[:3] == first + [{"role": "assistant", "content": [text_block("First.")]}]
    assert second[3] == {"role": "user", "content": "two"}
    convo = client.get(f"/api/coach/conversations/{cid}", headers=owner_headers()).json()
    assert convo["title"] == "one" and len(convo["messages"]) == 4


def test_failed_turn_stores_nothing(client, fake, clean_db):
    fake.turns = [([], [], "refusal")]
    cid = new_conversation(client)
    assert events(send(client, cid))[-1]["type"] == "error"
    with clean_db.begin() as c:
        assert c.execute(text("select count(*) from coach_messages")).scalar() == 0


def test_conversation_list_newest_first(client, fake):
    fake.turns = [answer("b"), answer("a")]
    a, b = new_conversation(client), new_conversation(client)
    send(client, b, "newer conversation")
    send(client, a, "older conversation, but just used")
    listed = client.get("/api/coach/conversations", headers=owner_headers()).json()
    assert [c["id"] for c in listed] == [a, b] and listed[0]["title"].startswith("older conversation")


def test_title_is_truncated(client, fake):
    fake.turns = [answer("ok")]
    cid = new_conversation(client)
    send(client, cid, "x" * 100)
    assert len(client.get(f"/api/coach/conversations/{cid}", headers=owner_headers()).json()["title"]) <= 61


def test_message_validation(client, fake):
    cid = new_conversation(client)
    for body in [{"text": ""}, {"text": "   "}, {"text": "x" * 4001}, {}]:
        r = client.post(f"/api/coach/conversations/{cid}/messages", json=body, headers=owner_headers())
        assert r.status_code == 422, body


def test_unknown_conversation(client, fake):
    assert client.get("/api/coach/conversations/999", headers=owner_headers()).status_code == 404
    assert send(client, 999).status_code == 404


def test_missing_api_key_is_a_setup_message(client, clean_db):
    app.dependency_overrides[get_settings] = lambda: replace(get_settings(), anthropic_api_key=None)
    app.dependency_overrides[coach.get_coach_engine] = lambda: clean_db
    r = client.post("/api/coach/conversations", headers=owner_headers())
    assert r.status_code == 503
    assert r.json()["detail"] == "The coach isn't set up yet: add ANTHROPIC_API_KEY in Vercel."
    with clean_db.begin() as c:
        cid = c.execute(text("insert into coach_conversations default values returning id")).scalar_one()
    assert send(client, cid).status_code == 503


def test_conversations_without_messages_are_not_listed(client, fake):
    fake.turns = [([], [], "refusal")]
    send(client, new_conversation(client))
    assert client.get("/api/coach/conversations", headers=owner_headers()).json() == []


def test_goals_active_first(client, clean_db):
    with clean_db.begin() as c:
        c.execute(text("insert into goals (text, status) values ('old', 'achieved'), ('new', 'active')"))
    assert [g["text"] for g in client.get("/api/coach/goals", headers=owner_headers()).json()] == ["new", "old"]


@pytest.mark.parametrize("method, path", [
    ("get", "/api/coach/conversations"), ("post", "/api/coach/conversations"),
    ("get", "/api/coach/conversations/1"), ("post", "/api/coach/conversations/1/messages"),
    ("get", "/api/coach/goals"),
])
def test_requires_owner(client, method, path):
    assert getattr(client, method)(path).status_code == 401
