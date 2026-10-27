from datetime import UTC, datetime

import pytest
from conftest import owner_headers
from sqlalchemy import text
from test_coach_loop import FakeLLM, answer, go, kinds, tool_use, tools_turn

from lockedin.app import app
from lockedin.coach.llm import CoachUnavailable
from lockedin.coach.sql import QueryRejected, run_readonly
from lockedin.coach.tools import SCHEMA_TEXT
from lockedin.config import get_settings

NOW = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)


def test_huge_results_are_refused_in_the_database(clean_db):
    with pytest.raises(QueryRejected, match="too large"):
        run_readonly(clean_db, "select repeat('x', 2000000) as blob")


def test_advisory_locks_dont_outlive_the_query(clean_db):
    with clean_db.connect() as c:
        run_readonly(clean_db, "select pg_advisory_lock(42)")
        held = c.execute(text("select count(*) from pg_locks where locktype = 'advisory' and objid = 42")).scalar()
    assert held == 0


def test_final_round_forbids_tools():
    class Recording(FakeLLM):
        def stream(self, *, system, messages, tools, tool_choice=None):
            self.calls.append({"tool_choice": tool_choice})
            yield from super().stream(system=system, messages=messages, tools=tools)

    llm = Recording([tools_turn(tool_use(i, "get_goals")) for i in range(2)] + [answer("done")])
    go(llm, max_rounds=2)
    choices = [c["tool_choice"] for c in llm.calls if "tool_choice" in c]
    assert choices[-1] == {"type": "none"} and choices[0] is None


def test_retry_after_bad_json_resets_the_partial_text():
    class Glitchy(FakeLLM):
        def stream(self, *, system, messages, tools, tool_choice=None):
            turn = self.turns[0]
            if turn == "glitch":
                self.turns.pop(0)
                yield {"type": "text", "text": "half a sen"}
                raise ValueError("bad tool json")
            yield from super().stream(system=system, messages=messages, tools=tools)

    _, events = go(Glitchy(["glitch", answer("Whole answer.")]))
    assert kinds(events) == ["text", "reset", "text", "done"]


def test_status_says_whether_the_coach_is_set_up(client):
    from dataclasses import replace
    h = owner_headers()
    app.dependency_overrides[get_settings] = lambda: replace(get_settings(), anthropic_api_key=None)
    assert client.get("/api/coach/status", headers=h).json() == {"ready": False, "model": "claude-opus-5-5",
                                                                 "spent_today_usd": 0.0, "daily_budget_usd": 5.0}
    app.dependency_overrides[get_settings] = lambda: replace(get_settings(), anthropic_api_key="sk-x")
    assert client.get("/api/coach/status", headers=h).json()["ready"] is True
    assert client.get("/api/coach/status").status_code == 401


def test_too_long_chat_gets_a_clear_message(monkeypatch):
    import anthropic
    import httpx

    from lockedin.coach.llm import AnthropicLLM

    llm = AnthropicLLM(api_key="sk-test", model="claude-opus-5-5")
    response = httpx.Response(400, request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"))
    err = anthropic.BadRequestError("prompt is too long: 1000001 tokens > 1000000 maximum", response=response,
                                    body={"type": "error", "error": {"type": "invalid_request_error",
                                                                      "message": "prompt is too long: 1000001 tokens > 1000000 maximum"}})

    def stream(**kw):
        raise err

    monkeypatch.setattr(llm.client.beta.messages, "stream", stream)
    with pytest.raises(CoachUnavailable, match="This chat got too long; start a new one."):
        list(llm.stream(system="S", messages=[], tools=[]))


def test_schema_text_describes_new_fields():
    for words in ("targets", "goal_id", "'gym'|'bike'|'run'|'swim'|'body'|'general'"):
        assert words in SCHEMA_TEXT
