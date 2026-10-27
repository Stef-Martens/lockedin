"""One owner message → streamed answer, running the coach's tools in between."""

import logging
import time
from collections.abc import Callable, Iterator

from lockedin.coach.llm import TOO_LONG, CoachLLM, CoachUnavailable, Final
from lockedin.coach.prompt import SYSTEM_PROMPT
from lockedin.coach.tools import TOOLS

log = logging.getLogger(__name__)

ANSWER_NOW = "You've used all the tool calls for this message. Answer now with what you have; no more tools."
OUT_OF_TIME = "You're out of time for this message. Answer now with what you have; no more tools."
JSON_RETRIES = 2

ToolRunner = Callable[[str, object], tuple[str, bool]]


def run_turn(llm: CoachLLM, *, history: list[dict], user_text: str, context: str, tool_runner: ToolRunner,
             max_rounds: int = 8, deadline: float | None = None,
             clock: Callable[[], float] = time.monotonic) -> Iterator[dict]:
    """Yields text/tool/done/error/usage events, plus `appended` events listing messages added to `history`.

    Each `appended` batch must be stored in one go: it always leaves the conversation valid to replay.
    The user and context messages wait for the model's first answer (a system message must be followed
    by an assistant turn), and a tool call waits for its results. Past `deadline` (a `clock()` value) no new
    tool round starts: the next round answers without tools, as after `max_rounds`.
    """
    pending = [{"role": "user", "content": user_text}, {"role": "system", "content": context}]

    def append(*messages: dict) -> Iterator[dict]:
        batch = [*pending, *messages]
        history.extend(batch)
        pending.clear()
        yield {"type": "appended", "messages": batch}

    def run_tool(name: str, args: object) -> tuple[str, bool]:
        try:
            return tool_runner(name, args)
        except Exception:
            log.exception("coach tool %s crashed", name)
            return f"The {name} tool failed. Try a different approach or tell the owner it isn't working.", True

    rounds = 0
    retries = 0
    final_round = False
    while True:
        final = None
        try:
            for item in llm.stream(system=SYSTEM_PROMPT, messages=history + pending, tools=TOOLS,
                                   tool_choice={"type": "none"} if final_round else None):
                if isinstance(item, Final):
                    final = item
                else:
                    yield item
        except CoachUnavailable as e:
            yield {"type": "error", "message": str(e)}
            return
        except ValueError:
            # Tool input JSON the SDK couldn't parse at all: there's no tool_use id to answer, so re-ask.
            retries += 1
            if retries <= JSON_RETRIES:
                yield {"type": "reset"}  # drop this round's partial text; the round is asked again
                continue
            yield {"type": "error", "message": "Something went wrong talking to the coach. Try again."}
            return
        except Exception:
            log.exception("coach turn failed")
            yield {"type": "error", "message": "Something went wrong talking to the coach. Try again."}
            return
        retries = 0
        if final.usage:
            yield {"type": "usage", "usage": final.usage}

        uses = [b for b in final.content if b.get("type") == "tool_use"]
        if final.stop_reason == "refusal":
            yield {"type": "error", "message": "I can't help with that one."}
            return
        if final.stop_reason == "model_context_window_exceeded":
            yield {"type": "error", "message": TOO_LONG}
            return
        if final.stop_reason == "max_tokens" and uses:
            yield {"type": "error", "message": "That answer got too long; try a narrower question."}
            return
        has_text = any(b.get("type") == "text" and b.get("text") for b in final.content)
        if not uses and not has_text:
            # An empty assistant turn can't be replayed, so it's never stored.
            yield {"type": "error", "message": "The coach didn't answer. Try again."}
            return
        if not uses:
            yield from append({"role": "assistant", "content": final.content})
            if final.stop_reason == "pause_turn":
                continue
            yield {"type": "done"}
            return
        if final_round:
            yield {"type": "error", "message": "That took too many steps; try a narrower question."}
            return

        results = []
        for use in uses:
            yield {"type": "tool", "name": use["name"], "status": "start"}
            content, is_error = run_tool(use["name"], use.get("input"))
            yield {"type": "tool", "name": use["name"], "status": "error" if is_error else "done"}
            results.append({"type": "tool_result", "tool_use_id": use["id"], "content": content, "is_error": is_error})
        yield from append({"role": "assistant", "content": final.content}, {"role": "user", "content": results})
        rounds += 1
        if rounds >= max_rounds:
            final_round = True
            pending.append({"role": "system", "content": ANSWER_NOW})
        elif deadline is not None and clock() >= deadline:
            final_round = True
            pending.append({"role": "system", "content": OUT_OF_TIME})
