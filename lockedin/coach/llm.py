"""The model behind the coach, behind a small interface so the loop can be tested without the API."""

import logging
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Protocol

log = logging.getLogger(__name__)

MAX_TOKENS = 64000
# Dropped from the history before the last fallback switch point; the fallback model can't use them.
PRE_FALLBACK_DROP = {"thinking", "redacted_thinking", "tool_use"}
TOO_LONG = "This chat got too long; start a new one."


@dataclass
class Final:
    content: list[dict]
    stop_reason: str
    # One entry per billed model attempt: model, input_tokens, output_tokens, cache_read_tokens, cache_write_tokens.
    usage: list[dict] = field(default_factory=list)


class CoachUnavailable(Exception):
    """The model can't be reached or refused the request; the message is safe to show the owner."""


class CoachLLM(Protocol):
    def stream(self, *, system: str, messages: list[dict], tools: list[dict],
               tool_choice: dict | None = None, output_format: dict | None = None) -> Iterator[dict | Final]:
        """Yields {"type": "text", "text": ...} deltas, then one Final."""


def echo_content(blocks: list[dict]) -> list[dict]:
    """The assistant content to keep in history: after a mid-output fallback, the internal blocks before
    the switch point are dropped, as the API requires when the turn is sent back."""
    last = max((i for i, b in enumerate(blocks) if b.get("type") == "fallback"), default=None)
    if last is None:
        return blocks
    return [b for i, b in enumerate(blocks) if i >= last or b.get("type") not in PRE_FALLBACK_DROP]


def usage_of(message: object, requested_model: str) -> list[dict]:
    """Token usage per billed attempt. After a refusal fallback, `usage.iterations` holds each attempt (top-level
    usage only covers the one that answered), each billed at its own model's prices."""
    u = getattr(message, "usage", None)
    if u is None:
        return []

    def row(x: object, model: str | None) -> dict:
        return {"model": model or requested_model, "input_tokens": getattr(x, "input_tokens", 0) or 0,
                "output_tokens": getattr(x, "output_tokens", 0) or 0,
                "cache_read_tokens": getattr(x, "cache_read_input_tokens", 0) or 0,
                "cache_write_tokens": getattr(x, "cache_creation_input_tokens", 0) or 0}

    attempts = [i for i in getattr(u, "iterations", None) or []
                if getattr(i, "type", None) in ("message", "fallback_message")]
    if attempts:
        return [row(i, getattr(i, "model", None)) for i in attempts]
    return [row(u, getattr(message, "model", None))]


def _error_message(e: Exception) -> str:
    """The API's own message (`error.message` in the body); the exception's text has the status code in front."""
    body = getattr(e, "body", None)
    error = body.get("error") if isinstance(body, dict) else None
    return str(error.get("message", "")) if isinstance(error, dict) else ""


def _prompt_too_long(e: Exception) -> bool:
    # The API has no dedicated error type for an over-long prompt: it's an invalid_request_error whose
    # message starts "prompt is too long: N tokens > M maximum".
    return getattr(e, "type", None) == "invalid_request_error" and \
        _error_message(e).lower().startswith("prompt is too long")


class AnthropicLLM:
    def __init__(self, api_key: str, model: str):
        import anthropic

        self._anthropic = anthropic
        self.client = anthropic.Anthropic(api_key=api_key, max_retries=2, timeout=120)
        self.model = model

    def stream(self, *, system: str, messages: list[dict], tools: list[dict],
               tool_choice: dict | None = None, output_format: dict | None = None) -> Iterator[dict | Final]:
        a = self._anthropic
        extra = {"tool_choice": tool_choice} if tool_choice else {}
        output_config = {"effort": "medium", **({"format": output_format} if output_format else {})}
        try:
            with self.client.beta.messages.stream(
                model=self.model,
                max_tokens=MAX_TOKENS,
                system=[{"type": "text", "text": system}],
                messages=messages,
                tools=tools,
                # A thinking block is bound to the system prompt and tools it was made with; after a deploy that
                # changes either, an old chat's blocks no longer match. Drop them rather than fail the request.
                thinking={"type": "adaptive", "block_binding": {"prefix_mismatch_behavior": "drop_block"}},
                output_config=output_config,
                cache_control={"type": "ephemeral"},
                betas=["server-side-fallback-2026-07-01", "thinking-binding-controls-2026-08-01"],
                fallbacks="default",
                **extra,
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
        except a.RequestTooLargeError:
            raise CoachUnavailable(TOO_LONG) from None
        except a.BadRequestError as e:
            if _prompt_too_long(e):
                raise CoachUnavailable(TOO_LONG) from None
            log.warning("coach API error 400: %s", e.message)
            raise CoachUnavailable("The coach request was rejected; try starting a new conversation.") from None
        except a.APIStatusError as e:
            log.warning("coach API error %s: %s", e.status_code, e.message)
            # Errors that arrive on an already-open stream carry the HTTP 200 of the stream itself.
            kind = (e.body or {}).get("error", {}).get("type") if isinstance(e.body, dict) else None
            if e.status_code >= 500 or e.status_code < 400 or kind in ("overloaded_error", "api_error"):
                raise CoachUnavailable("Claude is having trouble right now; try again in a minute.") from None
            raise CoachUnavailable("The coach request was rejected; try starting a new conversation.") from None
        content = final.to_dict(mode="json")["content"]
        try:
            usage = usage_of(final, self.model)
        except Exception:  # accounting must never cost the owner an answer
            log.exception("couldn't read coach usage")
            usage = []
        yield Final(content=echo_content(content), stop_reason=final.stop_reason or "end_turn", usage=usage)
