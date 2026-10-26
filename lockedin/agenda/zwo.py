"""Structured Zwift workouts: validation, the .zwo file Zwift reads, its file name and a one-line summary."""

import re
import unicodedata
import xml.etree.ElementTree as ET
from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_TOTAL_S = 6 * 3600
Power = Annotated[float, Field(ge=0.3, le=1.6, description="Fraction of FTP")]
Seconds = Annotated[int, Field(ge=10, le=14400)]


class _Block(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Ramp(_Block):
    """Zwift ramps from from_power to to_power (PowerLow → PowerHigh in the file)."""
    type: Literal["warmup", "cooldown"]
    duration_s: Seconds
    from_power: Power
    to_power: Power


class Steady(_Block):
    type: Literal["steady"]
    duration_s: Seconds
    power: Power


class Intervals(_Block):
    type: Literal["intervals"]
    repeat: Annotated[int, Field(ge=1, le=30)]
    on_s: Seconds
    off_s: Seconds
    on_power: Power
    off_power: Power


class Free(_Block):
    type: Literal["free"]
    duration_s: Seconds


Block = Annotated[Ramp | Steady | Intervals | Free, Field(discriminator="type")]


def block_seconds(b) -> int:
    return b.repeat * (b.on_s + b.off_s) if isinstance(b, Intervals) else b.duration_s


class ZwiftWorkout(BaseModel):
    model_config = ConfigDict(extra="forbid")
    blocks: list[Block] = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def _not_too_long(self):
        if sum(block_seconds(b) for b in self.blocks) > MAX_TOTAL_S:
            raise ValueError("A Zwift workout can be at most 6 hours.")
        return self


def duration_s(w: ZwiftWorkout) -> int:
    return sum(block_seconds(b) for b in w.blocks)


def _num(x: float) -> str:
    return f"{x:g}"


def strip_control(s: str, keep: str = "") -> str:
    """Drop control characters (no XML file can hold most of them), apart from those in `keep`."""
    return "".join(c for c in s if c in keep or unicodedata.category(c) != "Cc")


def render(title: str, day: date, note: str | None, w: ZwiftWorkout) -> str:
    root = ET.Element("workout_file")
    for tag, value in (("author", "LockedIn"), ("name", f"{day.isoformat()} {strip_control(title)}"),
                       ("description", strip_control(note or "", "\t\n")), ("sportType", "bike")):
        ET.SubElement(root, tag).text = value
    workout = ET.SubElement(root, "workout")
    for b in w.blocks:
        if isinstance(b, Ramp):
            ET.SubElement(workout, "Warmup" if b.type == "warmup" else "Cooldown", {
                "Duration": str(b.duration_s), "PowerLow": _num(b.from_power), "PowerHigh": _num(b.to_power)})
        elif isinstance(b, Steady):
            ET.SubElement(workout, "SteadyState", {"Duration": str(b.duration_s), "Power": _num(b.power)})
        elif isinstance(b, Intervals):
            ET.SubElement(workout, "IntervalsT", {
                "Repeat": str(b.repeat), "OnDuration": str(b.on_s), "OffDuration": str(b.off_s),
                "OnPower": _num(b.on_power), "OffPower": _num(b.off_power)})
        else:
            ET.SubElement(workout, "FreeRide", {"Duration": str(b.duration_s)})
    ET.indent(root)
    return ET.tostring(root, encoding="unicode") + "\n"


def filename(title: str, day: date) -> str:
    """'2026-10-29 Sweet Spot 3x10.zwo': safe on any file system, never a path."""
    plain = "".join(c for c in unicodedata.normalize("NFKD", title) if not unicodedata.combining(c))  # Vélo → Velo
    safe = re.sub(r"[^A-Za-z0-9 ._()×x-]", "-", plain).strip(" .-") or "workout"
    return f"{day.isoformat()} {safe}"[:80].rstrip(" .") + ".zwo"


def _minutes(s: int) -> str:
    return f"{round(s / 60)}′" if s >= 60 else f"{s}″"


def summary(w: ZwiftWorkout, ftp: float | None) -> str:
    """'65′ · 3 × 10′ at 151 W': total time and the hardest part, in watts when the FTP is known."""
    def power(p: float) -> str:
        return f"{round(p * ftp)} W" if ftp else f"{round(p * 100)}%"

    def load(b) -> float:
        if isinstance(b, Intervals):
            return b.on_power * b.on_s * b.repeat
        if isinstance(b, Steady):
            return b.power * b.duration_s
        if isinstance(b, Ramp):
            return max(b.from_power, b.to_power) * b.duration_s
        return 0

    total = _minutes(duration_s(w))
    hardest = max(w.blocks, key=load)
    if isinstance(hardest, Intervals):
        return f"{total} · {hardest.repeat} × {_minutes(hardest.on_s)} at {power(hardest.on_power)}"
    if isinstance(hardest, Steady):
        return f"{total} · {_minutes(hardest.duration_s)} at {power(hardest.power)}"
    if isinstance(hardest, Ramp):
        return f"{total} · ramp to {power(max(hardest.from_power, hardest.to_power))}"
    return f"{total} · free ride"
