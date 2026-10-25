"""One owner message → streamed answer, running the coach's tools in between."""

import logging
from collections.abc import Callable, Iterator

from lockedin.coach.llm import CoachLLM, CoachUnavailable, Final
from lockedin.coach.prompt import SYSTEM_PROMPT
from lockedin.coach.tools import TOOLS

log = logging.getLogger(__name__)

ANSWER_NOW = "You've used all the tool calls for this message. Answer now with what you have; no more tools."
JSON_RETRIES = 2

ToolRunner = Callable[[str, object], tuple[str, bool]]


def run_turn(llm: CoachLLM, *, history: list[dict], user_text: str, context: str, tool_runner: ToolRunner,
             max_rounds: int = 8) -> Iterator[dict]:
    """Yields text/tool/done/error events, plus an `appended` event for each message added to `history`.

    The user and context messages are only appended once the model has answered, so a failed turn leaves
    the stored conversation valid (a system message must be followed by an assistant turn).
    """
    pending = [{"role": "user", "content": user_text}, {"role": "system", "content": context}]

    def append(message: dict) -> Iterator[dict]:
        for m in [*pending, message]:
            history.append(m)
            yield {"type": "appended", "message": m}
        pending.clear()

    rounds = 0
    retries = 0
    while True:
        final = None
        try:
            for item in llm.stream(system=SYSTEM_PROMPT, messages=history + pending, tools=TOOLS):
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
                continue
            yield {"type": "error", "message": "Something went wrong talking to the coach. Try again."}
            return
        except Exception:
            log.exception("coach turn failed")
            yield {"type": "error", "message": "Something went wrong talking to the coach. Try again."}
            return
        retries = 0

        uses = [b for b in final.content if b.get("type") == "tool_use"]
        if final.stop_reason == "refusal":
            yield {"type": "error", "message": "I can't help with that one."}
            return
        if final.stop_reason == "max_tokens" and uses:
            yield {"type": "error", "message": "That answer got too long; try a narrower question."}
            return
        if not uses:
            yield from append({"role": "assistant", "content": final.content})
            if final.stop_reason == "pause_turn":
                continue
            yield {"type": "done"}
            return
        if rounds >= max_rounds:
            yield {"type": "error", "message": "That took too many steps; try a narrower question."}
            return

        yield from append({"role": "assistant", "content": final.content})
        results = []
        for use in uses:
            yield {"type": "tool", "name": use["name"], "status": "start"}
            content, is_error = tool_runner(use["name"], use.get("input"))
            yield {"type": "tool", "name": use["name"], "status": "error" if is_error else "done"}
            results.append({"type": "tool_result", "tool_use_id": use["id"], "content": content, "is_error": is_error})
        yield from append({"role": "user", "content": results})
        rounds += 1
        if rounds >= max_rounds:
            pending.append({"role": "system", "content": ANSWER_NOW})
