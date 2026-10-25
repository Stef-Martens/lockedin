"""Parse Hevy's "Export workouts" CSV, by column name, tolerating added/removed/reordered columns."""

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from lockedin.timeutil import parse_local

DATE_FORMATS = ["%d %b %Y, %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M"]
REQUIRED = ("title", "start_time", "exercise_title")
LBS_TO_KG = 0.45359237
MILES_TO_KM = 1.609344


@dataclass
class HevySet:
    exercise_title: str
    exercise_order: int
    set_index: int
    set_type: str
    weight_kg: float | None
    reps: int | None
    distance_km: float | None
    duration_s: int | None
    rpe: float | None
    superset_id: str | None
    notes: str | None


@dataclass
class HevyWorkout:
    title: str
    description: str | None
    start_at: datetime
    end_at: datetime
    sets: list[HevySet] = field(default_factory=list)


@dataclass
class HevyParseResult:
    workouts: list[HevyWorkout]
    skipped: list[tuple[int, str]]


def _norm_header(h: str) -> str:
    return re.sub(r"\s+", "_", re.sub(r"[()]", "", h.strip().lower()))


def _blank(v: str | None) -> str | None:
    v = (v or "").strip()
    return v or None


def _num(v: str | None, scale: float = 1.0) -> float | None:
    v = _blank(v)
    return None if v is None else float(v.replace(",", ".")) * scale


def _int(v: str | None) -> int | None:
    n = _num(v)
    return None if n is None else int(round(n))


def parse_hevy_csv(text: str) -> HevyParseResult:
    reader = csv.reader(io.StringIO(text.lstrip("﻿"), newline=""))
    try:
        header = [_norm_header(h) for h in next(reader)]
    except StopIteration:
        raise ValueError("The file is empty.") from None
    missing = [c for c in REQUIRED if c not in header]
    if missing:
        raise ValueError(f"Missing column(s): {', '.join(missing)}. Is this a Hevy workout export?")

    workouts: dict[tuple[str, str], HevyWorkout] = {}
    orders: dict[tuple[str, str], dict[str, int]] = {}
    skipped: list[tuple[int, str]] = []

    for row_no, values in enumerate(reader, start=2):
        if not any(v.strip() for v in values):
            continue
        r = dict(zip(header, values))
        try:
            title, start_raw, exercise = r["title"].strip(), r["start_time"].strip(), r["exercise_title"].strip()
            if not exercise:
                raise ValueError("no exercise name")
            start = parse_local(start_raw, DATE_FORMATS)
            end_raw = _blank(r.get("end_time"))
            end = parse_local(end_raw, DATE_FORMATS) if end_raw else start + timedelta(hours=1)
            if "weight_kg" in r:
                weight = _num(r.get("weight_kg"))
            else:
                weight = _num(r.get("weight_lbs"), LBS_TO_KG)
            if "distance_km" in r:
                distance = _num(r.get("distance_km"))
            else:
                distance = _num(r.get("distance_miles"), MILES_TO_KM)
            reps, duration, rpe = _int(r.get("reps")), _int(r.get("duration_seconds")), _num(r.get("rpe"))
        except ValueError as e:
            skipped.append((row_no, str(e)))
            continue

        key = (title, start_raw)
        w = workouts.get(key)
        if w is None:
            w = workouts[key] = HevyWorkout(title, _blank(r.get("description")), start, max(end, start))
            orders[key] = {}
        order = orders[key].setdefault(exercise, len(orders[key]))
        idx = _int(r.get("set_index"))
        w.sets.append(HevySet(
            exercise_title=exercise,
            exercise_order=order,
            set_index=idx if idx is not None else sum(s.exercise_title == exercise for s in w.sets),
            set_type=_blank(r.get("set_type")) or "normal",
            weight_kg=round(weight, 2) if weight is not None else None,
            reps=reps,
            distance_km=distance,
            duration_s=duration,
            rpe=rpe,
            superset_id=_blank(r.get("superset_id")),
            notes=_blank(r.get("exercise_notes")),
        ))
    return HevyParseResult(list(workouts.values()), skipped)
