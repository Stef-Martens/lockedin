"""Agenda items: saving and editing them, listing a week with what got done, and the Zwift file feed."""

import json
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import Connection, text

from lockedin.agenda.zwo import ZwiftWorkout, duration_s, filename, render, summary
from lockedin.fitness import ftp_at
from lockedin.focus.sessions import counted
from lockedin.plan.routines import routines
from lockedin.timeutil import TZ

Sport = Literal["gym", "bike", "run", "swim", "rest", "other"]
FIELDS = "id, day, sport, title, note, optional, routine, zwift, zwift_synced_at, sort, source"
# Edits to these change the Zwift file, so it has to be fetched again.
FILE_FIELDS = {"title", "note", "day", "zwift"}


class ItemIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    day: date
    sport: Sport
    title: str = Field(max_length=80)
    note: str | None = Field(None, max_length=500)
    optional: bool = False
    routine: str | None = Field(None, max_length=120)
    zwift: ZwiftWorkout | None = None
    sort: int = Field(0, ge=0, le=100)

    @field_validator("title")
    @classmethod
    def _title(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Give it a title.")
        return v.strip()

    @model_validator(mode="after")
    def _fits_sport(self):
        if self.zwift and self.sport != "bike":
            raise ValueError("Only bike items can have a Zwift workout.")
        if self.routine and self.sport != "gym":
            raise ValueError("Only gym items can have a routine.")
        return self


class ItemPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    day: date | None = None
    sport: Sport | None = None
    title: str | None = Field(None, max_length=80)
    note: str | None = Field(None, max_length=500)
    optional: bool | None = None
    routine: str | None = Field(None, max_length=120)
    zwift: ZwiftWorkout | None = None
    sort: int | None = Field(None, ge=0, le=100)


def local_today(now: datetime) -> date:
    return now.astimezone(TZ).date()


def monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _check_routine(conn: Connection, now: datetime, routine: str | None) -> None:
    if not routine:
        return
    names = [r.title for r in routines(conn, now)]
    if routine not in names:
        known = ", ".join(f"'{n}'" for n in names) or "none yet (do a Hevy routine and import it first)"
        raise ValueError(f"Unknown routine '{routine}'. Your routines: {known}.")


def _zwift_json(item: ItemIn) -> str | None:
    return json.dumps(item.zwift.model_dump()) if item.zwift else None


def _out(row, ftp: float | None, today: date, done: dict[int, int]) -> dict:
    zwift = None
    if row.zwift:
        w = ZwiftWorkout(**row.zwift)
        zwift = {"blocks": row.zwift["blocks"], "duration_s": duration_s(w), "summary": summary(w, ftp),
                 "filename": filename(row.title, row.day)}
    status = None if not zwift or row.day < today else ("synced" if row.zwift_synced_at else "pending")
    return {"id": row.id, "day": row.day.isoformat(), "sport": row.sport, "title": row.title, "note": row.note,
            "optional": row.optional, "routine": row.routine, "zwift": zwift, "zwift_status": status,
            "sort": row.sort, "source": row.source, "done": row.id in done, "activity_id": done.get(row.id)}


def _ticks(conn: Connection, rows: list, start: date, end: date) -> dict[int, int]:
    """item id → activity id that ticks it. Each activity ticks one item; items with a routine match first."""
    acts = conn.execute(text(
        "select a.id, a.sport, (a.start_at at time zone 'Europe/Brussels')::date as day, w.title "
        f"from activities a left join gym_workouts w on w.activity_id = a.id where {counted('a')} "
        "and a.start_at >= :s and a.start_at < :e order by a.start_at"
    ), {"s": datetime.combine(start, time(), TZ), "e": datetime.combine(end + timedelta(days=1), time(), TZ)}).all()
    by_day = defaultdict(list)
    for a in acts:
        by_day[a.day].append(a)
    used: set[int] = set()
    done: dict[int, int] = {}
    for item in sorted(rows, key=lambda r: (r.day, 0 if r.routine else 1, r.sort, r.id)):
        for a in by_day[item.day]:
            if a.id in used:
                continue
            fits = (a.sport == "gym" and (not item.routine or a.title == item.routine)) if item.sport == "gym" \
                else item.sport in ("bike", "run", "swim") and a.sport == item.sport
            if fits:
                used.add(a.id)
                done[item.id] = a.id
                break
    return done


def items_between(conn: Connection, now: datetime, start: date, end: date) -> list[dict]:
    rows = conn.execute(text(
        f"select {FIELDS} from agenda_items where day between :s and :e order by day, sort, id"
    ), {"s": start, "e": end}).all()
    done = _ticks(conn, rows, start, end)
    ftp = ftp_at(conn, now)
    return [_out(r, ftp, local_today(now), done) for r in rows]


def week(conn: Connection, now: datetime, any_day: date | None) -> dict:
    start = monday(any_day or local_today(now))
    return {"week_start": start.isoformat(), "today": local_today(now).isoformat(),
            "items": items_between(conn, now, start, start + timedelta(days=6))}


def get_item(conn: Connection, now: datetime, item_id: int) -> dict:
    row = conn.execute(text(f"select {FIELDS} from agenda_items where id = :i"), {"i": item_id}).first()
    if row is None:
        raise LookupError(f"There's no agenda item {item_id}.")
    return next(i for i in items_between(conn, now, row.day, row.day) if i["id"] == item_id)


def create(conn: Connection, now: datetime, item: ItemIn, source: str) -> dict:
    _check_routine(conn, now, item.routine)
    item_id = conn.execute(text(
        "insert into agenda_items (day, sport, title, note, optional, routine, zwift, sort, source) "
        "values (:day, :sport, :title, :note, :optional, :routine, cast(:zwift as jsonb), :sort, :source) returning id"
    ), {**item.model_dump(exclude={"zwift"}), "zwift": _zwift_json(item), "source": source}).scalar_one()
    return get_item(conn, now, item_id)


def update(conn: Connection, now: datetime, item_id: int, patch: ItemPatch) -> dict:
    row = conn.execute(text(f"select {FIELDS} from agenda_items where id = :i for update"), {"i": item_id}).first()
    if row is None:
        raise LookupError(f"There's no agenda item {item_id}.")
    changes = patch.model_dump(exclude_unset=True)
    current = {k: getattr(row, k) for k in ItemIn.model_fields}
    merged = ItemIn(**{**current, **changes})  # re-checks the combination (e.g. a routine on a run)
    if "routine" in changes:
        _check_routine(conn, now, merged.routine)
    reset = ", zwift_synced_at = null" if FILE_FIELDS & changes.keys() else ""
    conn.execute(text(
        "update agenda_items set day = :day, sport = :sport, title = :title, note = :note, optional = :optional, "
        f"routine = :routine, zwift = cast(:zwift as jsonb), sort = :sort, updated_at = now(){reset} where id = :id"
    ), {**merged.model_dump(exclude={"zwift"}), "zwift": _zwift_json(merged), "id": item_id})
    return get_item(conn, now, item_id)


def delete(conn: Connection, item_id: int) -> None:
    if conn.execute(text("delete from agenda_items where id = :i returning id"), {"i": item_id}).first() is None:
        raise LookupError(f"There's no agenda item {item_id}.")


def zwift_feed(conn: Connection, now: datetime) -> list[dict]:
    """The .zwo files that belong in Zwift now: bike workouts from today on. Marks them as fetched."""
    rows = conn.execute(text(
        f"select {FIELDS} from agenda_items where sport = 'bike' and zwift is not null and day >= :today "
        "order by day, sort, id"
    ), {"today": local_today(now)}).all()
    if rows:
        conn.execute(text("update agenda_items set zwift_synced_at = :now where id = any(:ids)"),
                     {"now": now, "ids": [r.id for r in rows]})
    return [{"item_id": r.id, "filename": filename(r.title, r.day),
             "content": render(r.title, r.day, r.note, ZwiftWorkout(**r.zwift))} for r in rows]
