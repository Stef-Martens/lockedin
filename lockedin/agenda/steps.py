"""A planned run as steps: warm-up, repeat blocks, cool-down. Models, the summary derived from them, and a one-line summary."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from lockedin.agenda.actual import _clock


class StepGoal(BaseModel):
    """How a step ends: after a time, after a distance, or when the runner presses the button."""
    model_config = ConfigDict(extra="forbid")
    time_s: int | None = Field(None, ge=30, le=10_800)
    distance_m: int | None = Field(None, ge=50, le=50_000)
    open: bool | None = None

    @model_validator(mode="after")
    def _one(self):
        if self.open is False:
            raise ValueError("A step's goal is open only when open is true; leave it out otherwise.")
        if sum(v is not None for v in (self.time_s, self.distance_m, self.open)) != 1:
            raise ValueError("A step's goal needs exactly one of time_s, distance_m or open.")
        return self


class StepTarget(BaseModel):
    """What a step aims for: a pace range (seconds per km) or a heart-rate zone, not both."""
    model_config = ConfigDict(extra="forbid")
    pace_low: int | None = Field(None, ge=150, le=720)
    pace_high: int | None = Field(None, ge=150, le=720)
    hr_zone: int | None = Field(None, ge=1, le=5)

    @model_validator(mode="after")
    def _one(self):
        if (self.pace_low is None) != (self.pace_high is None):
            raise ValueError("A step's pace needs both pace_low and pace_high.")
        if self.pace_low is not None and self.pace_low > self.pace_high:
            raise ValueError("A step's pace_low must be the faster (smaller) pace, at most pace_high.")
        if self.pace_low is not None and self.hr_zone is not None:
            raise ValueError("A step aims for a pace or a heart-rate zone, not both.")
        if self.pace_low is None and self.hr_zone is None:
            raise ValueError("A step's target needs a pace or a heart-rate zone; leave the target out for none.")
        return self


class Step(BaseModel):
    model_config = ConfigDict(extra="forbid")
    goal: StepGoal
    target: StepTarget | None = None


class BlockStep(Step):
    kind: Literal["work", "recovery"]


class Block(BaseModel):
    model_config = ConfigDict(extra="forbid")
    repeat: int = Field(ge=1, le=20)
    steps: list[BlockStep] = Field(min_length=1, max_length=10)


class RunSteps(BaseModel):
    model_config = ConfigDict(extra="forbid")
    warmup: Step | None = None
    blocks: list[Block] = Field(min_length=1, max_length=10)
    cooldown: Step | None = None


def expand(steps: dict) -> list[dict]:
    """The steps in run order, repeats unrolled."""
    out = []

    def add(kind: str, step: dict, repeated: bool = False):
        out.append({"kind": kind, "goal": step["goal"], "target": step.get("target"), "repeated": repeated})

    if steps.get("warmup"):
        add("warmup", steps["warmup"])
    for block in steps["blocks"]:
        for _ in range(block["repeat"]):
            for s in block["steps"]:
                add(s["kind"], s, block["repeat"] >= 2)
    if steps.get("cooldown"):
        add("cooldown", steps["cooldown"])
    return out


def derive(steps: RunSteps) -> dict:
    """The summary targets of a stepped run; a total or range outside the Targets limits is left None."""
    flat = expand(steps.model_dump(exclude_none=True))
    goals = [s["goal"] for s in flat]

    def total(key: str, lo: int, hi: int) -> int | None:
        if not all(key in g for g in goals):
            return None
        n = sum(g[key] for g in goals)
        return n if lo <= n <= hi else None

    work = [s["target"] or {} for s in flat if s["kind"] == "work"]
    paced = [t for t in work if "pace_low" in t]
    zones = {t.get("hr_zone") for t in work}
    return {
        "duration_s": total("time_s", 60, 21_600),
        "distance_m": total("distance_m", 100, 100_000),
        "pace_low": min((t["pace_low"] for t in paced), default=None),
        "pace_high": max((t["pace_high"] for t in paced), default=None),
        "hr_zone": zones.pop() if len(zones) == 1 else None,
    }


def _time(s: int) -> str:
    m, sec = divmod(s, 60)
    if not m:
        return f"{sec}″"
    return f"{m}′" if not sec else f"{m}′{sec:02d}″"


def _distance(m: int, metres_only: bool = False) -> str:
    return f"{m} m" if m < 1000 or metres_only else f"{m / 1000:g} km"


def _pace(low: int, high: int, suffix: str = "") -> str:
    return f"@ {_clock(low)}{suffix}" if low == high else f"@ {_clock(low)}–{_clock(high)}{suffix}"


def _goal_words(goal: dict) -> str:
    if "time_s" in goal:
        return _time(goal["time_s"])
    if "distance_m" in goal:
        return _distance(goal["distance_m"])
    return ""


def _target_words(target: dict | None) -> str:
    if not target:
        return ""
    if target.get("pace_low") is not None:
        return _pace(target["pace_low"], target["pace_high"])
    return f"Z{target['hr_zone']}" if target.get("hr_zone") else ""


def _step_words(step: dict, label: str = "") -> str:
    words = [_goal_words(step["goal"]), label, _target_words(step.get("target"))]
    return " ".join(p for p in words if p) or "open"


def summary_line(sport: str, targets: dict | None) -> str | None:
    """One line saying what a run or swim asks for, from its steps or else its summary targets."""
    if not targets:
        return None
    if targets.get("steps"):
        steps = targets["steps"]
        parts = []
        if steps.get("warmup"):
            parts.append(_step_words(steps["warmup"], "warm-up"))
        for block in steps["blocks"]:
            inner = ", ".join(_step_words(s, "jog" if s["kind"] == "recovery" else "") for s in block["steps"])
            parts.append(f"{block['repeat']} × ({inner})" if block["repeat"] >= 2 else inner)
        if steps.get("cooldown"):
            parts.append(_step_words(steps["cooldown"], "cool-down"))
        return " · ".join(parts)
    swim = sport == "swim"
    pace = None
    if targets.get("pace_low") is not None and targets.get("pace_high") is not None:
        pace = _pace(targets["pace_low"], targets["pace_high"], "/100 m" if swim else "")
    parts = [
        _distance(targets["distance_m"], metres_only=swim) if targets.get("distance_m") else "",
        _time(targets["duration_s"]) if targets.get("duration_s") else "",
        pace or "",
        f"Z{targets['hr_zone']}" if targets.get("hr_zone") else "",
    ]
    return " ".join(p for p in parts if p) or None
