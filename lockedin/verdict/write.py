"""The one model call: a label and a few sentences about a workout, from the server's facts."""

import json
from dataclasses import dataclass

from lockedin.coach.llm import CoachLLM, CoachUnavailable, Final

LABELS = ("on_plan", "close", "off_plan")

SYSTEM = """\
You are the personal training coach inside LockedIn, a private training tracker used by one person: the owner. \
They have just finished a workout. Write a short verdict on it that they will find saved next to the session: a \
label and a few sentences. You get the facts as JSON: the workout, the plan it was compared against (if any), the \
comparison the app already computed, recent similar sessions, and the owner's goals.

Rules:
- Use only numbers present in the facts. Never work out new ones or invent any.
- Say what's missing instead of guessing (no heart rate, no splits, no recent sessions).
- Plain words, 2 to 4 sentences, no headings, no lists, no praise for its own sake. Say plainly when it went badly.
- Compare with recent sessions only when they are in the facts ("faster than last week at the same heart rate").
- You are not a doctor. No medical advice. On a session after time off, compare with the easy_back note.

What the facts can't tell you:
- step_results are matched by the plan's order and lengths from the start of the run, not read from the \
watch's own laps. If the owner may not have followed the plan (for example, the paces look nothing like the \
plan's), don't describe the rows as blocks they ran: say the run doesn't appear to follow the plan's steps, and \
use the km splits and zones.
- When step_results is null, speak about km splits, zones and totals only; never about individual blocks.
- On a stepped run, the km splits include the warm-up and the recovery, so a slower km isn't by itself a miss.
- When rest_day is true, the owner's plan for that day was to rest; say so if it matters.

Labels, one of:
- on_plan: done as planned, targets met within reason.
- close: mostly as planned, with a clear miss.
- off_plan: a different session from the plan, or targets clearly missed.
Pick the one that fits the facts. Write the text for the owner, talking to them directly as "you".
"""

SCHEMA = {
    "type": "object",
    "properties": {"label": {"type": "string", "enum": list(LABELS)}, "text": {"type": "string"}},
    "required": ["label", "text"],
    "additionalProperties": False,
}


class VerdictFailed(Exception):
    """No usable verdict came back. `usage` is what the attempt was billed, so the caller can still record it."""

    def __init__(self, message: str, usage: list[dict] | None = None):
        super().__init__(message)
        self.usage = usage or []


@dataclass
class Written:
    label: str
    text: str
    usage: list[dict]


def write(llm: CoachLLM, facts: dict, planned: bool) -> Written:
    """`planned` is whether an agenda item is ticked; without one the label is always `unplanned`."""
    message = {"role": "user", "content": "The facts about the workout:\n" + json.dumps(facts, ensure_ascii=False)}
    final = None
    try:
        for event in llm.stream(system=SYSTEM, messages=[message], tools=[],
                                output_format={"type": "json_schema", "schema": SCHEMA}):
            if isinstance(event, Final):
                final = event
    except CoachUnavailable as e:
        raise VerdictFailed(str(e)) from e
    if final is None or final.stop_reason == "refusal":
        raise VerdictFailed("The model gave no verdict.", final.usage if final else [])
    raw = "".join(b.get("text", "") for b in final.content if b.get("type") == "text")
    try:
        data = json.loads(raw)
        label, text = data["label"], data["text"].strip()
    except (ValueError, KeyError, TypeError, AttributeError):
        raise VerdictFailed("The verdict wasn't in the expected shape.", final.usage) from None
    if label not in LABELS or not text:
        raise VerdictFailed("The verdict was empty or had an unknown label.", final.usage)
    return Written(label=label if planned else "unplanned", text=text, usage=final.usage)
