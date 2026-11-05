import json

import pytest
from test_coach_loop import FakeLLM, text_block

from lockedin.coach.llm import CoachUnavailable, Final
from lockedin.verdict.write import SCHEMA, SYSTEM, VerdictFailed, write

FACTS = {"workout": {"sport": "run"}, "step_results": None}


def reply(label="close", text="Mostly there."):
    s = json.dumps({"label": label, "text": text})
    return ([], [text_block(s)], "end_turn")


def test_write_returns_label_and_text():
    out = write(FakeLLM([reply()]), FACTS, planned=True)
    assert (out.label, out.text, out.usage) == ("close", "Mostly there.", [])


def test_unplanned_overrides_the_label():
    assert write(FakeLLM([reply("on_plan")]), FACTS, planned=False).label == "unplanned"


def test_sends_facts_and_no_tools():
    llm = FakeLLM([reply()])
    write(llm, FACTS, planned=True)
    call = llm.calls[0]
    assert call["tools"] == [] and call["system"] == SYSTEM
    assert call["output_format"] == {"type": "json_schema", "schema": SCHEMA}
    assert json.loads(call["messages"][0]["content"].split("\n", 1)[1]) == FACTS


def test_prompt_states_the_limits_of_step_results():
    assert "step_results is null" in SYSTEM and "doesn't appear to follow the plan's steps" in SYSTEM
    assert "include the warm-up" in SYSTEM


@pytest.mark.parametrize("turn", [
    ([], [text_block("")], "end_turn"),
    ([], [], "end_turn"),
    ([], [text_block("not json")], "end_turn"),
    ([], [text_block('{"label": "great", "text": "x"}')], "end_turn"),
    ([], [text_block('{"label": "close"}')], "end_turn"),
    ([], [text_block('{"label": "close", "text": "  "}')], "end_turn"),
    ([], [], "refusal"),
    CoachUnavailable("Claude is busy right now; try again in a minute."),
])
def test_unusable_answers_fail(turn):
    with pytest.raises(VerdictFailed):
        write(FakeLLM([turn]), FACTS, planned=True)


USAGE = [{"model": "m", "input_tokens": 10, "output_tokens": 5, "cache_read_tokens": 0, "cache_write_tokens": 0}]


class Billed:
    """Yields a Final carrying usage, as the real client does."""

    def __init__(self, content, stop="end_turn"):
        self.final = Final(content=content, stop_reason=stop, usage=USAGE)

    def stream(self, **kw):
        yield self.final


def test_text_is_found_after_thinking_and_fallback_blocks():
    content = [{"type": "thinking", "thinking": "", "signature": "s"}, {"type": "fallback"},
               text_block(json.dumps({"label": "on_plan", "text": "Right on."}))]
    out = write(Billed(content), FACTS, planned=True)
    assert (out.label, out.text, out.usage) == ("on_plan", "Right on.", USAGE)


@pytest.mark.parametrize("content,stop", [([], "refusal"), ([text_block("not json")], "end_turn"),
                                           ([text_block('{"label": "x", "text": "y"}')], "end_turn")])
def test_a_failed_attempt_still_carries_its_usage(content, stop):
    with pytest.raises(VerdictFailed) as e:
        write(Billed(content, stop), FACTS, planned=True)
    assert e.value.usage == USAGE


def test_failure_without_a_final_has_no_usage():
    with pytest.raises(VerdictFailed) as e:
        write(FakeLLM([CoachUnavailable("busy")]), FACTS, planned=True)
    assert e.value.usage == []
