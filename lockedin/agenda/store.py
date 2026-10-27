"""Agenda items: saving and editing them, listing a week with what got done, and the Zwift file feed."""

import json
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import Connection, text

from lockedin.agenda.actual import result_line
from lockedin.agenda.steps import RunSteps, derive
from lockedin.agenda.zwo import ZwiftWorkout, duration_s, filename, render, strip_control, summary
from lockedin.fitness import ftp_at
from lockedin.focus.sessions import counted
from lockedin.plan.routines import routines
from lockedin.timeoff import CATEGORIES, WORDS, entry_on, item_clash, off_on
from lockedin.timeutil import TZ

Sport = Literal["gym", "bike", "run", "swim", "rest", "other"]
FIELDS = "id, day, sport, title, note, optional, routine, zwift, zwift_synced_at, sort, source, targets, goal_id"
PACE = {"run": (150, 720), "swim": (50, 300)}  # s/km for runs, s/100 m for swims


class Targets(BaseModel):
    """What a run or swim aims for. Paces: seconds per km (run) or per 100 m (swim)."""
    model_config = ConfigDict(extra="forbid")
    distance_m: int | None = Field(None, ge=100, le=100_000)
    duration_s: int | None = Field(None, ge=60, le=21_600)
    pace_low: int | None = Field(None, ge=50, le=720)
    pace_high: int | None = Field(None, ge=50, le=720)
    hr_zone: int | None = Field(None, ge=1, le=5)
    steps: RunSteps | None = None

    @model_validator(mode="after")
    def _from_steps(self):
        """With steps, the summary fields are always recomputed from them; whatever was sent is ignored."""
        if self.steps:
            for key, value in derive(self.steps).items():
                setattr(self, key, value)
        return self

    @model_validator(mode="after")
    def _paces(self):
        if self.pace_low and self.pace_high and self.pace_low > self.pace_high:
            raise ValueError("pace_low must be the faster (smaller) pace, at most pace_high.")
        return self
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
    targets: Targets | None = None
    goal_id: int | None = None
    sort: int = Field(0, ge=0, le=100)

    @field_validator("title")
    @classmethod
    def _title(cls, v: str) -> str:
        v = strip_control(v).strip()
        if not v:
            raise ValueError("Give it a title.")
        return v

    @field_validator("note")
    @classmethod
    def _note(cls, v: str | None) -> str | None:
        return strip_control(v, "\t\n") if v is not None else None

    @model_validator(mode="after")
    def _fits_sport(self):
        if self.zwift and self.sport != "bike":
            raise ValueError("Only bike items can have a Zwift workout.")
        if self.routine and self.sport != "gym":
            raise ValueError("Only gym items can have a routine.")
        if self.targets:
            if self.sport not in PACE:
                raise ValueError("Only runs and swims have targets.")
            if self.targets.steps and self.sport != "run":
                raise ValueError("Steps are for runs only.")
            lo, hi = PACE[self.sport]
            for p in (self.targets.pace_low, self.targets.pace_high):
                if p is not None and not lo <= p <= hi:
                    unit = "s/km" if self.sport == "run" else "s/100 m"
                    raise ValueError(f"A {self.sport} pace must be between {lo} and {hi} {unit}.")
            if self.targets.hr_zone and self.sport != "run":
                raise ValueError("Heart-rate zones are for runs only.")
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
    targets: Targets | None = None
    goal_id: int | None = None
    sort: int | None = Field(None, ge=0, le=100)

    @field_validator("title")
    @classmethod
    def _title(cls, v: str | None) -> str | None:
        return strip_control(v) if v is not None else None

    @field_validator("note")
    @classmethod
    def _note(cls, v: str | None) -> str | None:
        return strip_control(v, "\t\n") if v is not None else None


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


def _check_time_off(conn: Connection, day: date, sport: str, routine: str | None) -> None:
    """The coach doesn't plan something that is off on that day."""
    if message := item_clash(conn, off_on(conn, day), {"sport": sport, "routine": routine}):
        raise ValueError(f"{message}, so I can't plan it then.")


def _zwift_json(item: ItemIn) -> str | None:
    return json.dumps(item.zwift.model_dump()) if item.zwift else None


def _targets_json(item: ItemIn) -> str | None:
    return json.dumps(item.targets.model_dump(exclude_none=True)) if item.targets else None


def _check_goal(conn: Connection, goal_id: int | None) -> None:
    if goal_id is not None and conn.execute(text(
            "select 1 from goals where id = :g and status = 'active'"), {"g": goal_id}).first() is None:
        raise ValueError(f"There's no active goal {goal_id}; use get_goals for the ids.")


def _goal_labels(conn: Connection, ids: set) -> dict[int, str]:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    return {r.id: (f"{r.text} ({r.target})" if r.target else r.text) for r in conn.execute(text(
        "select id, text, target from goals where id = any(:i)"), {"i": list(ids)})}


def _out(row, ftp: float | None, today: date, done: dict[int, int], goals: dict[int, str] | None = None) -> dict:
    zwift = None
    if row.zwift:
        w = ZwiftWorkout(**row.zwift)
        zwift = {"blocks": row.zwift["blocks"], "duration_s": duration_s(w), "summary": summary(w, ftp),
                 "filename": filename(row.title, row.day)}
    status = None if not zwift or row.day < today else ("synced" if row.zwift_synced_at else "pending")
    return {"id": row.id, "day": row.day.isoformat(), "sport": row.sport, "title": row.title, "note": row.note,
            "optional": row.optional, "routine": row.routine, "zwift": zwift, "zwift_status": status,
            "sort": row.sort, "source": row.source, "done": row.id in done, "activity_id": done.get(row.id),
            "targets": row.targets, "goal_id": row.goal_id, "goal": (goals or {}).get(row.goal_id)}


def _ticks(conn: Connection, rows: list, start: date, end: date) -> dict[int, int]:
    """item id → activity id that ticks it. Each activity ticks one item. First the exact matches (a gym
    workout titled like the item's routine, a ride for a ride); then a gym item takes any gym workout left that
    day (the Hevy title was changed); last a rest day takes whatever is left (the optional spin was done).
    Within a pass, main items go before optional ones, so one ride ticks the planned ride, not the extra spin."""
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

    def exact(item, a) -> bool:
        if item.sport == "gym":
            return a.sport == "gym" and (not item.routine or a.title == item.routine)
        return item.sport in ("bike", "run", "swim") and a.sport == item.sport

    passes = (exact, lambda item, a: item.sport == "gym" and a.sport == "gym", lambda item, a: item.sport == "rest")
    ordered = sorted(rows, key=lambda r: (r.day, bool(r.optional), 0 if r.routine else 1, r.sort, r.id))
    for fits in passes:
        for item in ordered:
            if item.id in done:
                continue
            a = next((a for a in by_day[item.day] if a.id not in used and fits(item, a)), None)
            if a is not None:
                used.add(a.id)
                done[item.id] = a.id
    return done


def items_between(conn: Connection, now: datetime, start: date, end: date, results: bool = False) -> list[dict]:
    """Items with done state; `results` adds the one-line result for done items (reads the activities)."""
    rows = conn.execute(text(
        f"select {FIELDS} from agenda_items where day between :s and :e order by day, sort, id"
    ), {"s": start, "e": end}).all()
    done = _ticks(conn, rows, start, end)
    ftp = ftp_at(conn, now)
    goals = _goal_labels(conn, {r.goal_id for r in rows})
    items = [_out(r, ftp, local_today(now), done, goals) for r in rows]
    offs: dict[date, dict[str, date]] = {}
    sets: dict[str, list] = {}
    for item, r in zip(items, rows, strict=True):
        off = offs.setdefault(r.day, off_on(conn, r.day))
        item["clash"] = item_clash(conn, off, item, sets)
        if item["zwift_status"] and "bike" in off:
            item["zwift_status"] = None  # not sent to Zwift: cycling is off that day
    for item in items:
        item["result"] = result_line(conn, item) if results and item["done"] else None
    return items


def _time_off(conn: Connection, days: list[date]) -> list[dict]:
    out = []
    for day in days:
        if (entry := entry_on(conn, day)) is None:
            continue
        off = off_on(conn, day)
        words = "everything off" if "all" in off else ", ".join(f"no {WORDS[c]}" for c in CATEGORIES if c in off)
        out.append({"day": day.isoformat(), "reason": entry["reason"], "label": entry["label"], "text": words})
    return out


def week(conn: Connection, now: datetime, any_day: date | None) -> dict:
    start = monday(any_day or local_today(now))
    days = [start + timedelta(days=i) for i in range(7)]
    return {"week_start": start.isoformat(), "today": local_today(now).isoformat(),
            "items": items_between(conn, now, start, days[-1], results=True), "time_off": _time_off(conn, days)}


def get_item(conn: Connection, now: datetime, item_id: int) -> dict:
    row = conn.execute(text(f"select {FIELDS} from agenda_items where id = :i"), {"i": item_id}).first()
    if row is None:
        raise LookupError(f"There's no agenda item {item_id}.")
    return next(i for i in items_between(conn, now, row.day, row.day) if i["id"] == item_id)


def create(conn: Connection, now: datetime, item: ItemIn, source: str) -> dict:
    _check_routine(conn, now, item.routine)
    _check_goal(conn, item.goal_id)
    if source == "coach":
        _check_time_off(conn, item.day, item.sport, item.routine)
    item_id = conn.execute(text(
        "insert into agenda_items (day, sport, title, note, optional, routine, zwift, targets, goal_id, sort, source) "
        "values (:day, :sport, :title, :note, :optional, :routine, cast(:zwift as jsonb), cast(:targets as jsonb), "
        ":goal_id, :sort, :source) returning id"
    ), {**item.model_dump(exclude={"zwift", "targets"}), "zwift": _zwift_json(item), "targets": _targets_json(item),
        "source": source}).scalar_one()
    return get_item(conn, now, item_id)


def update(conn: Connection, now: datetime, item_id: int, patch: ItemPatch, source: str = "manual") -> dict:
    row = conn.execute(text(f"select {FIELDS} from agenda_items where id = :i for update"), {"i": item_id}).first()
    if row is None:
        raise LookupError(f"There's no agenda item {item_id}.")
    changes = patch.model_dump(exclude_unset=True)
    current = {k: getattr(row, k) for k in ItemIn.model_fields}
    merged = ItemIn(**{**current, **changes})  # re-checks the combination (e.g. a routine on a run)
    if "routine" in changes:
        _check_routine(conn, now, merged.routine)
    if "goal_id" in changes:
        _check_goal(conn, merged.goal_id)
    if source == "coach" and {"day", "sport", "routine"} & changes.keys():
        _check_time_off(conn, merged.day, merged.sport, merged.routine)
    reset = ", zwift_synced_at = null" if FILE_FIELDS & changes.keys() else ""
    conn.execute(text(
        "update agenda_items set day = :day, sport = :sport, title = :title, note = :note, optional = :optional, "
        f"routine = :routine, zwift = cast(:zwift as jsonb), targets = cast(:targets as jsonb), goal_id = :goal_id, "
        f"sort = :sort, updated_at = now(){reset} where id = :id"
    ), {**merged.model_dump(exclude={"zwift", "targets"}), "zwift": _zwift_json(merged), "targets": _targets_json(merged),
        "id": item_id})
    return get_item(conn, now, item_id)


def delete(conn: Connection, item_id: int) -> None:
    if conn.execute(text("delete from agenda_items where id = :i returning id"), {"i": item_id}).first() is None:
        raise LookupError(f"There's no agenda item {item_id}.")


def zwift_feed(conn: Connection, now: datetime) -> list[dict]:
    """The .zwo files that belong in Zwift now: bike workouts from today on (not on days cycling is off), with names unique even on a
    case-insensitive disk. Nothing is marked as in Zwift until the Mac confirms it wrote the file."""
    rows = conn.execute(text(
        f"select {FIELDS} from agenda_items where sport = 'bike' and zwift is not null and day >= :today "
        "order by day, sort, id"
    ), {"today": local_today(now)}).all()
    bike_off = {d: "bike" in off_on(conn, d) for d in {r.day for r in rows}}
    rows = [r for r in rows if not bike_off[r.day]]
    taken: set[str] = set()
    out = []
    for r in rows:
        name = filename(r.title, r.day)
        n = 2
        while name.lower() in taken:
            name = filename(r.title, r.day).removesuffix(".zwo") + f" ({n}).zwo"
            n += 1
        taken.add(name.lower())
        out.append({"item_id": r.id, "filename": name, "content": render(r.title, r.day, r.note, ZwiftWorkout(**r.zwift))})
    return out


def confirm_in_zwift(conn: Connection, now: datetime, item_ids: list[int]) -> int:
    """The Mac wrote (or already had) these files in Zwift's folder."""
    if not item_ids:
        return 0
    return conn.execute(text("update agenda_items set zwift_synced_at = :now where id = any(:ids) and zwift is not null"),
                        {"now": now, "ids": item_ids}).rowcount
