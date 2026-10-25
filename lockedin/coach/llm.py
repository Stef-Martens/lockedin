"""The model behind the coach, behind a small interface so the loop can be tested without the API."""

import logging
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Protocol

log = logging.getLogger(__name__)

MAX_TOKENS = 64000
# Dropped from the history before the last fallback switch point; the fallback model can't use them.
PRE_FALLBACK_DROP = {"thinking", "redacted_thinking", "tool_use"}


@dataclass
class Final:
    content: list[dict]
    stop_reason: str


class CoachUnavailable(Exception):
    """The model can't be reached or refused the request; the message is safe to show the owner."""


class CoachLLM(Protocol):
    def stream(self, *, system: str, messages: list[dict], tools: list[dict]) -> Iterator[dict | Final]:
        """Yields {"type": "text", "text": ...} deltas, then one Final."""


def echo_content(blocks: list[dict]) -> list[dict]:
    """The assistant content to keep in history: after a mid-output fallback, the internal blocks before
    the switch point are dropped, as the API requires when the turn is sent back."""
    last = max((i for i, b in enumerate(blocks) if b.get("type") == "fallback"), default=None)
    if last is None:
        return blocks
    return [b for i, b in enumerate(blocks) if i >= last or b.get("type") not in PRE_FALLBACK_DROP]


class AnthropicLLM:
    def __init__(self, api_key: str, model: str):
        import anthropic

        self._anthropic = anthropic
        self.client = anthropic.Anthropic(api_key=api_key, max_retries=2, timeout=120)
        self.model = model

    def stream(self, *, system: str, messages: list[dict], tools: list[dict]) -> Iterator[dict | Final]:
        a = self._anthropic
        try:
            with self.client.beta.messages.stream(
                model=self.model,
                max_tokens=MAX_TOKENS,
                system=[{"type": "text", "text": system}],
                messages=messages,
                tools=tools,
                thinking={"type": "adaptive"},
                output_config={"effort": "medium"},
                cache_control={"type": "ephemeral"},
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            ) as stream:
                for event in stream:
                    if event.type == "text":
                        yield {"type": "text", "text": event.text}
                final = stream.get_final_message()
        except a.AuthenticationError:
            raise CoachUnavailable("The Anthropic API key was rejected; check ANTHROPIC_API_KEY.") from None
        except a.RateLimitError:
            raise CoachUnavailable("Claude is busy right now; try again in a minute.") from None
        except a.APIConnectionError:
            raise CoachUnavailable("Couldn't reach Claude; check the connection and try again.") from None
        except a.APIStatusError as e:
            log.warning("coach API error %s: %s", e.status_code, e.message)
            if e.status_code >= 500:
                raise CoachUnavailable("Claude is having trouble right now; try again in a minute.") from None
            raise CoachUnavailable("The coach request was rejected; try starting a new conversation.") from None
        content = final.to_dict(mode="json")["content"]
        yield Final(content=echo_content(content), stop_reason=final.stop_reason or "end_turn")
