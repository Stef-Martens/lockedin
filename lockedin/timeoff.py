"""Time off (vacation or injury) with per-activity restrictions, and what is off on a given day."""

import calendar
import json
from datetime import date, timedelta
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import Connection, text

CATEGORIES = ("run", "bike", "swim", "upper", "core", "lower", "all")
REGIONS = {"upper": ("arms", "back", "chest", "shoulders"), "core": ("core",), "lower": ("legs",)}
WORDS = {"run": "running", "bike": "cycling", "swim": "swimming", "upper": "upper body", "core": "core",
         "lower": "lower body"}
Category = Literal["run", "bike", "swim", "upper", "core", "lower", "all"]


class Restriction(BaseModel):
    category: Category
    until: date


class TimeOffIn(BaseModel):
    reason: Literal["vacation", "injury"]
    label: str | None = Field(None, max_length=60)
    start: date
    restrictions: list[Restriction] = Field(min_length=1, max_length=len(CATEGORIES))

    @field_validator("label")
    @classmethod
    def _label(cls, v: str | None) -> str | None:
        return (v or "").strip() or None

    @model_validator(mode="after")
    def _check(self):
        if len({r.category for r in self.restrictions}) != len(self.restrictions):
            raise ValueError("Each activity can only be listed once.")
        if any(r.until < self.start for r in self.restrictions):
            raise ValueError("Every restriction must end on or after the start.")
        return self


def _entry(row) -> dict:
    rs = sorted(({"category": r["category"], "until": date.fromisoformat(r["until"])} for r in row.restrictions),
                key=lambda r: CATEGORIES.index(r["category"]))
    return {"id": row.id, "reason": row.reason, "label": row.label, "start": row.start_day,
            "end": max(r["until"] for r in rs), "restrictions": rs}


def _all(conn: Connection) -> list[dict]:
    rows = conn.execute(text("select id, reason, label, start_day, restrictions from time_off order by start_day, id"))
    return [_entry(r) for r in rows]


def entries(conn: Connection, since: date | None = None) -> list[dict]:
    """Entries ordered by start; with `since`, only those that end on or after it."""
    return [e for e in _all(conn) if since is None or e["end"] >= since]


def _get(conn: Connection, entry_id: int) -> dict:
    row = conn.execute(text("select id, reason, label, start_day, restrictions from time_off where id = :i"),
                       {"i": entry_id}).first()
    if row is None:
        raise LookupError(f"There's no time off {entry_id}.")
    return _entry(row)


def _params(body: TimeOffIn) -> dict:
    rs = sorted(body.restrictions, key=lambda r: CATEGORIES.index(r.category))
    return {"reason": body.reason, "label": body.label, "start": body.start,
            "rs": json.dumps([{"category": r.category, "until": r.until.isoformat()} for r in rs])}


def create(conn: Connection, body: TimeOffIn) -> dict:
    new_id = conn.execute(text(
        "insert into time_off (reason, label, start_day, restrictions) "
        "values (:reason, :label, :start, cast(:rs as jsonb)) returning id"), _params(body)).scalar_one()
    return _get(conn, new_id)


def update(conn: Connection, entry_id: int, body: TimeOffIn) -> dict:
    if conn.execute(text(
        "update time_off set reason = :reason, label = :label, start_day = :start, restrictions = cast(:rs as jsonb) "
        "where id = :id returning id"), {**_params(body), "id": entry_id}).first() is None:
        raise LookupError(f"There's no time off {entry_id}.")
    return _get(conn, entry_id)


def delete(conn: Connection, entry_id: int) -> None:
    if conn.execute(text("delete from time_off where id = :i returning id"), {"i": entry_id}).first() is None:
        raise LookupError(f"There's no time off {entry_id}.")


def off_on(conn: Connection, day: date) -> dict[str, date]:
    """Category -> the latest day it stays off, for what is off on `day`. `all` switches every category off."""
    off: dict[str, date] = {}
    for e in _all(conn):
        if e["start"] > day:
            continue
        for r in e["restrictions"]:
            if r["until"] < day:
                continue
            for c in CATEGORIES if r["category"] == "all" else (r["category"],):
                off[c] = max(off.get(c, r["until"]), r["until"])
    return {c: off[c] for c in CATEGORIES if c in off}


def away_on(conn: Connection, day: date) -> bool:
    return "all" in off_on(conn, day)


def off_muscles(conn: Connection, day: date) -> dict[str, date]:
    """Muscle key -> the day it is back, for muscles in a region that is off on `day`."""
    off = off_on(conn, day)
    by_region = {reg: off[c] for c, regs in REGIONS.items() if c in off for reg in regs}
    if not by_region:
        return {}
    rows = conn.execute(text("select key, region from muscles where region = any(:r) order by sort, key"),
                        {"r": list(by_region)})
    return {r.key: by_region[r.region] for r in rows}


def entry_on(conn: Connection, day: date) -> dict | None:
    """The entry covering `day`; the one that started last wins."""
    covering = [e for e in _all(conn) if e["start"] <= day <= e["end"]]
    return max(covering, key=lambda e: (e["start"], e["id"]), default=None)


def back_from(conn: Connection, day: date, category: str, within_days: int) -> dict | None:
    """The entry whose restriction on `category` (or `all`) ended in the `within_days` days before `day`."""
    lo, hi = day - timedelta(days=within_days), day - timedelta(days=1)
    hits = [(r["until"], e) for e in _all(conn) for r in e["restrictions"]
            if r["category"] in (category, "all") and lo <= r["until"] <= hi]
    return max(hits, key=lambda h: (h[0], h[1]["id"]))[1] if hits else None


def _fmt(d: date) -> str:
    return f"{d.day} {calendar.month_abbr[d.month]}"


def describe(off: dict[str, date]) -> str:
    """"no running until 17 Dec, no upper body until 2 Jan", or "everything off until 27 Dec"."""
    if "all" in off:
        return f"everything off until {_fmt(off['all'])}"
    return ", ".join(f"no {WORDS[c]} until {_fmt(off[c])}" for c in CATEGORIES if c in off)
