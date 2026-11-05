"""The one model call: a label and a few sentences about a workout, from the server's facts."""

import json
from dataclasses import dataclass

from lockedin.coach.llm import CoachLLM, CoachUnavailable, Final

LABELS = ("on_plan", "close", "off_plan")

SYSTEM = """\
You are the personal training coach inside LockedIn, a private training tracker used by one person: the owner. \
They have just finished a workout. Write a short verdict on it that they will find saved next to the session: a \
label and a few sentences. Start with how it went against the plan, the main point first (with no plan, \
how it went). You get the facts as JSON: the workout, the plan it was compared against (if any), the \
comparison the app already computed, recent similar sessions, and the owner's goals.

Rules:
- Use only numbers present in the facts. Never invent any, and don't work out new ones, other than converting units to read them.
- Units in the facts: paces are seconds per km (swims: seconds per 100 m: swim_pace_s_per_100m), as in pace, \
pace_s_per_km, avg_pace_s_per_km, pace_low and pace_high; on a swim, pace_low and pace_high are per 100 m too. Distances are metres (distance_m, metres, goal \
distance_m), except a gym row's distance_km, which is kilometres, and the km in a split, which is its number. \
Durations and zone values are seconds (duration_s, moving_s, seconds, time_s, start_s, end_s, zones). \
Converting these for reading is expected (5:38/km, 8 km, 22 minutes); show them that way, never raw seconds or \
metres. Working out anything else stays forbidden.
- Mention missing data (no heart rate, no splits, no recent sessions) only if it changes the verdict. Never talk about how the data was collected or matched, and never say there is no per-block breakdown.
- Plain words, 2 to 4 sentences; keep it short and to the point. No headings, no lists, no praise for its own sake. Say plainly when it went badly.
- Compare with recent sessions only when they are in the facts ("faster than last week at the same heart rate").
- You are not a doctor. No medical advice. On a session after time off, compare with the easy_back note.

How to read the blocks and the rest of the facts:
- blocks holds the watch's own laps and is exact. When the plan has steps, each block is one planned step: judge the \
run on its work blocks (pace_s_per_km and avg_hr against planned_target; in_target says whether a block hit it), and \
name blocks ("the first block", "the last two") rather than km. in_target covers pace or heart rate only: also check \
seconds or metres (whichever the planned goal is in) and the number of work blocks against the plan, and say so when a work block was cut short or there are fewer work blocks than planned \
(a short cool-down isn't worth a mention). On a run with plan steps, km splits mix blocks and recoveries: use them \
only when blocks is null.
- When the plan has steps and blocks.follows_plan is false, say the run didn't follow the plan's steps, and don't \
judge the blocks against the targets (planned_goal, planned_target and in_target are null then).
- Without plan steps (no plan, a rest day, or a plan with only a pace or heart-rate target), blocks are just the \
watch's laps: describe them if useful, never call it a failure to follow the plan, and the km splits are usable.
- On a run, when blocks is null, speak about km splits, zones and totals only; never about individual blocks.
- When the plan has steps but blocks is null, plan.pace_low and plan.pace_high belong to the work steps only: \
don't judge the run's overall average pace against them. Use the km splits and zones, and be modest about the label.
- When plan is null, judge the workout itself and don't talk about being on or off plan (the label you must \
still give is replaced by the app).
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


def _parse(content: list[dict]) -> dict:
    """The JSON in the text blocks. After a mid-stream fallback the answer is whatever follows the last
    `fallback` block; the text before it is the abandoned attempt. If that doesn't parse, try all the text joined."""
    last = max((i for i, b in enumerate(content) if b.get("type") == "fallback"), default=-1)

    def joined(blocks: list[dict]) -> str:
        return "".join(b.get("text", "") for b in blocks if b.get("type") == "text")

    try:
        return json.loads(joined(content[last + 1:]))
    except ValueError:
        if last < 0:
            raise
        return json.loads(joined(content))


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
    try:
        data = _parse(final.content)
        label, text = data["label"], data["text"].strip()
    except (ValueError, KeyError, TypeError, AttributeError):
        raise VerdictFailed("The verdict wasn't in the expected shape.", final.usage) from None
    if label not in LABELS or not text:
        raise VerdictFailed("The verdict was empty or had an unknown label.", final.usage)
    return Written(label=label if planned else "unplanned", text=text, usage=final.usage)
