import copy
from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from lockedin.coach.llm import CoachUnavailable, Final, echo_content
from lockedin.coach.loop import ANSWER_NOW, run_turn
from lockedin.coach.prompt import SYSTEM_PROMPT, turn_context


def text_block(s):
    return {"type": "text", "text": s}


def tool_use(i, name, args=None):
    return {"type": "tool_use", "id": f"tu_{i}", "name": name, "input": args or {}}


class FakeLLM:
    """Plays scripted turns: each is (text deltas, content blocks, stop_reason) or an exception to raise."""

    def __init__(self, turns):
        self.turns = list(turns)
        self.calls = []

    def stream(self, *, system, messages, tools):
        self.calls.append({"system": system, "messages": copy.deepcopy(messages), "tools": tools})
        turn = self.turns.pop(0)
        if isinstance(turn, Exception):
            raise turn
        deltas, content, stop = turn
        for d in deltas:
            yield {"type": "text", "text": d}
        yield Final(content=content, stop_reason=stop)


def answer(s):
    return ([s], [text_block(s)], "end_turn")


def tools_turn(*uses):
    return ([], list(uses), "tool_use")


def runner(results=None):
    calls = []

    def run(name, args):
        calls.append((name, args))
        return (results or {}).get(name, (f"{name} result", False))

    run.calls = calls
    return run


def go(llm, history=None, tool_runner=None, **kw):
    history = history if history is not None else []
    events = list(run_turn(llm, history=history, user_text="What should I focus on?", context="CTX",
                           tool_runner=tool_runner or runner(), **kw))
    return history, events


def kinds(events):
    return [e["type"] for e in events if e["type"] != "appended"]


def test_text_answer_streams_and_appends():
    llm = FakeLLM([answer("Ride easy today.")])
    history, events = go(llm)
    assert kinds(events) == ["text", "done"]
    assert [m["role"] for m in history] == ["user", "system", "assistant"]
    assert history[0]["content"] == "What should I focus on?" and history[1]["content"] == "CTX"
    assert [e["message"] for e in events if e["type"] == "appended"] == history
    assert llm.calls[0]["system"] == SYSTEM_PROMPT


def test_one_tool_round_replays_the_assistant_content_unchanged():
    use = tool_use(1, "get_focus_facts")
    thinking = {"type": "thinking", "thinking": "", "signature": "sig"}
    llm = FakeLLM([([], [thinking, use], "tool_use"), answer("Do triceps.")])
    run = runner({"get_focus_facts": ('{"coverage": []}', False)})
    history, events = go(llm, tool_runner=run)
    assert run.calls == [("get_focus_facts", {})]
    assert [e for e in events if e["type"] == "tool"] == [
        {"type": "tool", "name": "get_focus_facts", "status": "start"},
        {"type": "tool", "name": "get_focus_facts", "status": "done"}]
    second = llm.calls[1]["messages"]
    assert second[2] == {"role": "assistant", "content": [thinking, use]}
    assert second[3] == {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "tu_1", "content": '{"coverage": []}', "is_error": False}]}
    assert [m["role"] for m in history] == ["user", "system", "assistant", "user", "assistant"]


def test_two_tool_calls_return_in_one_message():
    llm = FakeLLM([tools_turn(tool_use(1, "get_goals"), tool_use(2, "get_schema")), answer("ok")])
    history, _ = go(llm)
    results = history[3]["content"]
    assert [r["tool_use_id"] for r in results] == ["tu_1", "tu_2"]


def test_tool_error_is_reported_and_the_loop_continues():
    llm = FakeLLM([tools_turn(tool_use(1, "run_sql", {"query": "drop table x"})), answer("Let me try another way.")])
    history, events = go(llm, tool_runner=runner({"run_sql": ("Only SELECT", True)}))
    assert history[3]["content"][0]["is_error"] is True
    assert {"type": "tool", "name": "run_sql", "status": "error"} in events
    assert kinds(events)[-1] == "done"


def test_refusal_is_an_error_and_leaves_history_untouched():
    llm = FakeLLM([([], [], "refusal")])
    history, events = go(llm)
    assert events[-1] == {"type": "error", "message": "I can't help with that one."}
    assert history == [] and not [e for e in events if e["type"] == "appended"]


def test_refusal_after_a_tool_round_keeps_the_answered_round():
    llm = FakeLLM([tools_turn(tool_use(1, "get_goals")), (["partial"], [text_block("partial")], "refusal")])
    history, events = go(llm)
    assert events[-1]["type"] == "error"
    assert [m["role"] for m in history] == ["user", "system", "assistant", "user"]


def test_truncated_tool_call_is_not_run():
    run = runner()
    llm = FakeLLM([([], [tool_use(1, "run_sql", {"query": "select"})], "max_tokens")])
    history, events = go(llm, tool_runner=run)
    assert run.calls == [] and history == []
    assert events[-1] == {"type": "error", "message": "That answer got too long; try a narrower question."}


def test_truncated_text_answer_is_kept():
    llm = FakeLLM([(["long..."], [text_block("long...")], "max_tokens")])
    history, events = go(llm)
    assert kinds(events) == ["text", "done"] and history[-1]["role"] == "assistant"


def test_tool_rounds_are_capped():
    llm = FakeLLM([tools_turn(tool_use(i, "get_goals")) for i in range(8)] + [answer("Here's what I found.")])
    run = runner()
    history, events = go(llm, tool_runner=run, max_rounds=8)
    assert len(run.calls) == 8
    last = llm.calls[-1]["messages"]
    assert last[-1] == {"role": "system", "content": ANSWER_NOW} and last[-2]["role"] == "user"
    assert len(llm.calls) == 9 and kinds(events)[-1] == "done"
    assert history[-2] == {"role": "system", "content": ANSWER_NOW}


def test_tools_after_the_cap_are_not_run():
    llm = FakeLLM([tools_turn(tool_use(i, "get_goals")) for i in range(3)])
    run = runner()
    history, events = go(llm, tool_runner=run, max_rounds=2)
    assert len(run.calls) == 2
    assert events[-1] == {"type": "error", "message": "That took too many steps; try a narrower question."}
    assert history[-1]["role"] == "user" and history[-1]["content"][0]["type"] == "tool_result"


def test_llm_failure_is_a_friendly_error():
    history, events = go(FakeLLM([CoachUnavailable("Claude is busy right now; try again in a minute.")]))
    assert events[-1] == {"type": "error", "message": "Claude is busy right now; try again in a minute."}
    assert history == []
    _, events = go(FakeLLM([RuntimeError("boom")]))
    assert events[-1] == {"type": "error", "message": "Something went wrong talking to the coach. Try again."}


def test_unparseable_tool_json_retries_the_round():
    llm = FakeLLM([ValueError("bad json"), answer("ok")])
    history, events = go(llm)
    assert kinds(events) == ["text", "done"] and len(llm.calls) == 2


def test_history_is_sent_as_prefix():
    old = [{"role": "user", "content": "hi"}, {"role": "system", "content": "OLD"},
           {"role": "assistant", "content": [text_block("hello")]}]
    llm = FakeLLM([answer("again")])
    go(llm, history=list(old))
    assert llm.calls[0]["messages"][:3] == old


def test_echo_content_drops_internal_blocks_before_a_fallback():
    blocks = [{"type": "thinking", "thinking": "", "signature": "s"}, text_block("Part"),
              tool_use(1, "get_goals"), {"type": "fallback", "from": {"model": "a"}, "to": {"model": "b"}},
              {"type": "thinking", "thinking": "", "signature": "t"}, text_block("rest"), tool_use(2, "get_schema")]
    assert [b["type"] for b in echo_content(blocks)] == ["text", "fallback", "thinking", "text", "tool_use"]
    assert echo_content([text_block("x")]) == [text_block("x")]


def test_turn_context_mentions_date_and_goal_checkin(conn):
    now = datetime(2026, 10, 26, 8, 0, tzinfo=UTC)
    ctx = turn_context(conn, now)
    assert "Monday 26 October 2026" in ctx and "check-in is due" in ctx
    conn.execute(text("update profile set last_goal_review_at = :t"), {"t": now - timedelta(days=10)})
    conn.execute(text("insert into goals (text) values ('Bench 100 kg')"))
    ctx = turn_context(conn, now)
    assert "not due" in ctx and "1 active goal" in ctx
    conn.execute(text("update profile set last_goal_review_at = :t"), {"t": now - timedelta(days=29)})
    assert "check-in is due" in turn_context(conn, now)


class _Stream:
    def __init__(self, message):
        self.message = message

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def __iter__(self):
        from types import SimpleNamespace
        yield SimpleNamespace(type="text", text="Hi")
        yield SimpleNamespace(type="content_block_stop")

    def get_final_message(self):
        return self.message


def test_anthropic_adapter_request_shape(monkeypatch):
    from types import SimpleNamespace

    from lockedin.coach.llm import AnthropicLLM

    llm = AnthropicLLM(api_key="sk-test", model="claude-opus-5-5")
    sent = {}
    message = SimpleNamespace(stop_reason="end_turn",
                              to_dict=lambda mode: {"content": [{"type": "text", "text": "Hi"}]})

    def stream(**kw):
        sent.update(kw)
        return _Stream(message)

    monkeypatch.setattr(llm.client.beta.messages, "stream", stream)
    out = list(llm.stream(system="SYS", messages=[{"role": "user", "content": "x"}], tools=[]))
    assert out == [{"type": "text", "text": "Hi"}, Final(content=[{"type": "text", "text": "Hi"}], stop_reason="end_turn")]
    assert sent["model"] == "claude-opus-5-5" and sent["fallbacks"] == "default"
    assert sent["betas"] == ["server-side-fallback-2026-07-01"] and sent["cache_control"] == {"type": "ephemeral"}
    assert sent["output_config"] == {"effort": "medium"} and sent["system"] == [{"type": "text", "text": "SYS"}]
