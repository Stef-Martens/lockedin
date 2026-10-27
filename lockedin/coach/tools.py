"""What the coach can do: read the schema, run read-only SQL, read focus facts, and read or save goals."""

import difflib
import json
from datetime import date, datetime, timedelta

from fastapi.encoders import jsonable_encoder
from pydantic import ValidationError
from sqlalchemy import Connection, Engine, text

from lockedin import timeoff
from lockedin.agenda import store as agenda
from lockedin.coach.sql import QueryRejected, run_readonly
from lockedin.focus.facts import focus_facts
from lockedin.goals.progress import progress
from lockedin.plan.goals import known_exercises

SCHEMA_TEXT = """\
Readable tables (Postgres; run_sql sees only these). Times are timestamptz shown in Europe/Brussels; weeks start Monday.
Metric units throughout.

activities: one row per recorded session.
  id, source ('zwift' | 'healthfit' = Apple Watch | 'hevy' = gym), sport ('bike'|'run'|'swim'|'gym'|'other'),
  sub_type (e.g. 'virtual_activity', 'walking', 'strength'), start_at, end_at, duration_s, moving_s,
  distance_m, elevation_m, avg_hr, max_hr, calories, avg_power, max_power, avg_cadence (bike rpm; run = strides/min,
  double it for steps/min), np (normalized power W), if_ (intensity factor vs FTP), tss, best_20m_power,
  avg_pace_s_per_km (run), swim_pace_s_per_100m, swim_lengths, swim_strokes, pool_length_m,
  superseded_by (not null = Apple Watch duplicate of another recording), hr_merged_from.
  COUNTED sessions (what totals, streaks and trends use):
    superseded_by is null and coalesce(sub_type, '') not like 'walking%'
gym_workouts: activity_id (= activities.id of the gym session), title, description.
gym_sets: workout_id (= gym_workouts.activity_id), exercise_id, exercise_order, set_index (0-based),
  set_type ('normal'|'warmup'|'failure'|'dropset'), weight_kg, reps, distance_km, duration_s, rpe, notes,
  e1rm (estimated 1-rep max, Epley, kg; null above 20 reps and for assisted lifts; bests and goals use sets of
  12 reps or fewer). Dumbbell weights are as logged: see profile.dumbbell_weights.
exercises: id, name (Hevy's exercise name), is_bodyweight.
library_exercises: name, equipment ('barbell'|'dumbbell'|'cable'|'machine'|'bodyweight'|'other'), related_to, ratio.
library_muscles: exercise_name, muscle_key, role ('primary'|'secondary'). Join exercises.name = exercise_name.
muscles: key, name, region, target_low, target_high (weekly effective sets: primary = 1, secondary = 0.5).
measurement_types: id, name (Weight, Chest, Left arm, ...), unit ('kg' | 'cm'), kind ('weight'|'tape'|'other').
measurements: type_id, measured_on (date), value, note. One body check-in = all rows on one measured_on.
ftp_history: effective_from (date), source ('zwift' = read from an ERG workout or Zwift's logs, 'owner' = typed in),
  ftp (W; an owner row without one hands back to Zwift), activity_id (the ride a Zwift value came from). A day's FTP
  is the newer of the latest Zwift and owner rows on or before it; Zwift's earliest value also covers older rides.
profile (single row): avoid_muscles (left-out muscle keys), never_exercises, coach_notes, date_of_birth, height_cm, sex, max_hr_override, ftp_override, resting_hr_override,
  dumbbell_weights ('pair' = logged weight is both dumbbells together, 'each' = per hand), reminder_weeks,
  last_goal_review_at.
agenda_items: id, day, sport ('gym'|'bike'|'run'|'swim'|'rest'|'other'), title, note, optional, routine (Hevy
  routine name for gym), zwift (jsonb workout blocks), targets (jsonb: distance_m, duration_s, pace_low/pace_high in
  s/km or s/100 m, hr_zone), goal_id (the goal it serves), source ('coach'|'manual'). Use get_agenda for done state.
goals: id, text, area ('gym'|'bike'|'run'|'swim'|'body'|'general'), target, exercise (exact lift name, if about one), status ('active'|'achieved'|'dropped'),
  source, created_at, updated_at.
time_off: id, reason ('vacation'|'injury'), label, start_day, restrictions (jsonb list of {category, until}; category 'run'|'bike'|'swim'|
  'upper'|'core'|'lower'|'all', until = the last day it stays off). An entry is off from start_day to its latest until.

Tips: prefer get_focus_facts for coverage, suggestions, zones, plateaus and wins; use SQL for anything else.
Results are capped at 200 rows, so aggregate in SQL (group by week, exercise, ...) instead of pulling raw rows.
"""


def _tool(name: str, description: str, properties: dict | None = None, required: list[str] | None = None) -> dict:
    return {
        "name": name,
        "description": description,
        "input_schema": {"type": "object", "properties": properties or {}, "required": required or [],
                         "additionalProperties": False},
        "eager_input_streaming": True,
    }


_BLOCK = {"type": "object", "required": ["type"], "properties": {
    "type": {"type": "string", "enum": ["warmup", "cooldown", "steady", "intervals", "free"]},
    "duration_s": {"type": "integer", "description": "warmup/cooldown/steady/free"},
    "from_power": {"type": "number", "description": "warmup/cooldown start, fraction of FTP (0.3-1.6)"},
    "to_power": {"type": "number", "description": "warmup/cooldown end, fraction of FTP"},
    "power": {"type": "number", "description": "steady, fraction of FTP"},
    "repeat": {"type": "integer"}, "on_s": {"type": "integer"}, "off_s": {"type": "integer"},
    "on_power": {"type": "number"}, "off_power": {"type": "number"}}}
MAX_AGENDA_CHANGES = 30
AGENDA_CHANGE = {"type": "object", "required": ["op"], "properties": {
    "op": {"type": "string", "enum": ["add", "update", "delete"]},
    "id": {"type": "integer", "description": "For update/delete: the item id from get_agenda."},
    "day": {"type": "string", "description": "YYYY-MM-DD"},
    "sport": {"type": "string", "enum": ["gym", "bike", "run", "swim", "rest", "other"]},
    "title": {"type": "string", "description": "Short, e.g. 'Sweet Spot 3x10' or the Hevy routine name for gym."},
    "note": {"type": "string"},
    "optional": {"type": "boolean"},
    "routine": {"type": "string", "description": "Gym only: one of the owner's Hevy routine names, exactly."},
    "zwift": {"type": "object", "properties": {"blocks": {"type": "array", "maxItems": 30, "items": _BLOCK}},
              "required": ["blocks"]},
    "targets": {"type": "object", "description": "Runs and swims: what to aim for.", "properties": {
        "distance_m": {"type": "integer"}, "duration_s": {"type": "integer"},
        "pace_low": {"type": "integer", "description": "Faster end: s/km for runs, s/100 m for swims"},
        "pace_high": {"type": "integer", "description": "Slower end, same unit"},
        "hr_zone": {"type": "integer", "description": "Runs only, 1-5"}}},
    "goal_id": {"type": "integer", "description": "The active goal this session serves (from get_goals)."}}}

TIME_OFF_ENTRY = {"type": "object", "required": ["reason", "start", "restrictions"], "properties": {
    "reason": {"type": "string", "enum": ["vacation", "injury"]},
    "label": {"type": "string", "description": "Short, e.g. 'Knee operation' or 'Ski trip'."},
    "start": {"type": "string", "description": "First day off, YYYY-MM-DD."},
    "restrictions": {"type": "array", "maxItems": 7, "items": {
        "type": "object", "required": ["category", "until"], "properties": {
            "category": {"type": "string", "enum": list(timeoff.CATEGORIES),
                         "description": "'all' = everything (a vacation); upper/core/lower = body regions."},
            "until": {"type": "string", "description": "Last day it stays off, YYYY-MM-DD."}}}}}}


TOOLS = [
    _tool("get_schema", "Describe the tables and columns run_sql can read, with units and meanings. "
          "Call this before writing your first SQL query in a conversation."),
    _tool("run_sql", "Run one read-only Postgres SELECT (or WITH ... SELECT) over the owner's training data. "
          "Returns columns and rows as JSON, at most 200 rows. Writes, multiple statements and private tables "
          "are refused.",
          {"query": {"type": "string", "description": "A single SELECT statement."}}, ["query"]),
    _tool("get_focus_facts", "The app's own analysis right now: HR/power zones, weekly muscle coverage against "
          "targets, gym suggestions with weights, run/bike session suggestions, easy/hard mix, plateaus, recent "
          "wins, streak and comeback state. Start here for 'what should I focus on' questions."),
    _tool("get_goals", "All of the owner's goals (active, achieved and dropped), newest first."),
    _tool("save_goal", "Create or change a goal. Only call this after the owner has explicitly agreed to the exact "
          "change in this conversation. 'create' needs text; 'update', 'achieved' and 'dropped' need goal_id.",
          {"action": {"type": "string", "enum": ["create", "update", "achieved", "dropped"]},
           "goal_id": {"type": "integer"},
           "text": {"type": "string", "description": "The goal in the owner's words, e.g. 'Bench press 100 kg'."},
           "area": {"type": "string", "enum": ["gym", "bike", "run", "swim", "body", "general"],
                    "description": "What kind of goal: the app steers by it (focus tips, planner, agenda)."},
           "target": {"type": "string", "description": "When or how it's measured, e.g. 'by March 2027'."},
           "exercise": {"type": "string", "description": "Exact exercise name when the goal is about one lift, "
                        "e.g. 'Bench Press (Barbell)'."}},
          ["action"]),
    _tool("mark_goals_reviewed", "Record that the periodic goal check-in happened (the owner confirmed or changed "
          "their goals), so the next one is due in about 4 weeks."),
    _tool("get_agenda", "The owner's agenda (planned sessions per day) with whether each was done. Defaults to this "
          "week and next.",
          {"from": {"type": "string", "description": "First day, YYYY-MM-DD."},
           "to": {"type": "string", "description": "Last day, YYYY-MM-DD (at most 62 days after from)."}}),
    _tool("save_agenda", "Add, change or delete agenda items. Only call this after the owner has clearly agreed to "
          "this exact plan or change in this conversation. All changes apply together or not at all. For Zwift "
          "rides, give structured `zwift.blocks` (powers as fractions of FTP); the app turns them into a Zwift "
          "workout file that the owner's Mac puts into Zwift. Don't put dates in titles.",
          {"changes": {"type": "array", "maxItems": MAX_AGENDA_CHANGES, "items": AGENDA_CHANGE}}, ["changes"]),
    _tool("save_time_off", "Record, change or remove time off: a vacation or an injury/operation with an end date per "
          "activity. Only call this after the owner has clearly agreed to the exact entry in this conversation. "
          "'create' needs entry; 'update' needs id and the whole entry; 'delete' needs id (the id is in the "
          "context line or the time_off table).",
          {"action": {"type": "string", "enum": ["create", "update", "delete"]},
           "id": {"type": "integer"}, "entry": TIME_OFF_ENTRY}, ["action"]),
]
SCHEMAS = {t["name"]: t["input_schema"] for t in TOOLS}
TYPES = {"string": str, "integer": int, "object": dict, "array": list, "number": (int, float), "boolean": bool}


def validate(schema: dict, args: object) -> str | None:
    """Why `args` doesn't fit the tool's input schema, or None."""
    if not isinstance(args, dict):
        return "Tool input must be a JSON object."
    props = schema["properties"]
    extra = set(args) - set(props)
    if extra:
        return f"Unknown field(s): {', '.join(sorted(extra))}."
    missing = [k for k in schema["required"] if k not in args]
    if missing:
        return f"Missing required field(s): {', '.join(missing)}."
    for key, value in args.items():
        spec = props[key]
        if not isinstance(value, TYPES[spec["type"]]) or (isinstance(value, bool) and spec["type"] != "boolean"):
            return f"Field '{key}' must be a {spec['type']}."
        if "enum" in spec and value not in spec["enum"]:
            return f"Field '{key}' must be one of {', '.join(spec['enum'])}."
    return None


GOAL_FIELDS = "id, text, area, target, exercise, status, source, created_at, updated_at"


def _goal(conn: Connection, goal_id: int) -> dict:
    return dict(conn.execute(text(f"select {GOAL_FIELDS} from goals where id = :i"), {"i": goal_id}).mappings().one())


def _mark_reviewed(conn: Connection, now: datetime) -> None:
    conn.execute(text("update profile set last_goal_review_at = :now where id = 1"), {"now": now})


def _save_goal(conn: Connection, args: dict, now: datetime) -> dict:
    action = args["action"]
    if args.get("exercise"):
        known = known_exercises(conn)
        if args["exercise"] not in known:
            close = difflib.get_close_matches(args["exercise"], known, n=3, cutoff=0.6)
            hint = f" Did you mean: {', '.join(repr(c) for c in close)}?" if close else ""
            raise ValueError(f"Unknown exercise {args['exercise']!r}; use the exact name from their history.{hint}")
    fields = {k: args[k].strip() or None for k in ("text", "area", "target", "exercise") if k in args}
    if action == "create":
        if not fields.get("text"):
            raise ValueError("'create' needs a non-empty text.")
        goal_id = conn.execute(text(
            "insert into goals (text, area, target, exercise, created_at, updated_at) "
            "values (:text, :area, :target, :exercise, :now, :now) returning id"),
            {"target": None, "exercise": None, **fields, "area": fields.get("area") or "general", "now": now}).scalar_one()
    else:
        if "goal_id" not in args:
            raise ValueError(f"'{action}' needs goal_id.")
        if "text" in fields and not fields["text"]:
            raise ValueError("A goal's text can't be empty.")
        if "area" in fields and not fields["area"]:
            fields["area"] = "general"
        status = {"achieved": "achieved", "dropped": "dropped"}.get(action)
        sets = [f"{k} = :{k}" for k in fields] + (["status = :status"] if status else []) + ["updated_at = :now"]
        goal_id = conn.execute(text(f"update goals set {', '.join(sets)} where id = :id returning id"),
                               {**fields, "status": status, "now": now, "id": args["goal_id"]}).scalar()
        if goal_id is None:
            raise ValueError(f"There is no goal with id {args['goal_id']}; call get_goals for the ids.")
    _mark_reviewed(conn, now)
    return _goal(conn, goal_id)


def _dump(value: object) -> str:
    return json.dumps(jsonable_encoder(value), ensure_ascii=False)


def _get_agenda(conn: Connection, args: dict, now: datetime) -> list[dict]:
    start = date.fromisoformat(args["from"]) if args.get("from") else agenda.monday(agenda.local_today(now))
    end = date.fromisoformat(args["to"]) if args.get("to") else start + timedelta(days=13)
    if end < start or (end - start).days > 62:
        raise ValueError("'to' must be on or after 'from', at most 62 days later.")
    return agenda.items_between(conn, now, start, end, results=True)


def _save_agenda(conn: Connection, args: dict, now: datetime) -> list[dict]:
    if len(args["changes"]) > MAX_AGENDA_CHANGES:
        raise ValueError(f"At most {MAX_AGENDA_CHANGES} changes at a time; split them up.")
    out = []
    with conn.begin_nested():  # all changes or none
        for n, change in enumerate(args["changes"], 1):
            try:
                if not isinstance(change, dict):
                    raise ValueError("each change must be an object")
                fields = {k: v for k, v in change.items() if k not in ("op", "id")}
                op = change.get("op")
                if op == "add":
                    out.append({"op": "added", **agenda.create(conn, now, agenda.ItemIn(**fields), "coach")})
                elif op in ("update", "delete"):
                    if type(change.get("id")) is not int:  # bool is an int to Python, not an id
                        raise ValueError(f"'{op}' needs the item's id (from get_agenda)")
                    if op == "update":
                        out.append({"op": "updated", **agenda.update(conn, now, change["id"], agenda.ItemPatch(**fields), "coach")})
                    else:
                        agenda.delete(conn, change["id"])
                        out.append({"op": "deleted", "id": change["id"]})
                else:
                    raise ValueError("op must be add, update or delete")
            except ValidationError as e:
                raise ValueError(f"Change {n}: " + "; ".join(
                    f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" if err["loc"] else err["msg"]
                    for err in e.errors())) from None
            except (ValueError, LookupError) as e:
                raise ValueError(f"Change {n}: {e}") from None
    return out


def _save_time_off(conn: Connection, args: dict) -> dict:
    action = args["action"]
    if action != "create" and type(args.get("id")) is not int:
        raise ValueError(f"'{action}' needs the id of the time off.")
    if action == "delete":
        timeoff.delete(conn, args["id"])
        return {"deleted": args["id"]}
    if "entry" not in args:
        raise ValueError(f"'{action}' needs the entry.")
    try:
        body = timeoff.TimeOffIn(**args["entry"])
    except ValidationError as e:
        raise ValueError("; ".join(
            f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" if err["loc"] else err["msg"].removeprefix("Value error, ")
            for err in e.errors())) from None
    return timeoff.create(conn, body) if action == "create" else timeoff.update(conn, args["id"], body)


def execute_tool(name: str, args: object, *, conn: Connection, engine: Engine, now: datetime) -> tuple[str, bool]:
    """Run one tool call. Returns (content, is_error); errors are messages the model can act on."""
    if name not in SCHEMAS:
        return f"There is no tool called '{name}'.", True
    problem = validate(SCHEMAS[name], args)
    if problem:
        return problem, True
    try:
        if name == "get_schema":
            return SCHEMA_TEXT, False
        if name == "run_sql":
            return _dump(run_readonly(engine, args["query"])), False
        if name == "get_focus_facts":
            return _dump(focus_facts(conn, now)), False
        if name == "get_goals":
            rows = [dict(r) for r in conn.execute(text(f"select {GOAL_FIELDS} from goals order by created_at desc, id desc")).mappings()]
            for g in rows:
                g["progress"] = progress(conn, now, g) if g["status"] == "active" else None
            return _dump(rows), False
        if name == "save_goal":
            return _dump(_save_goal(conn, args, now)), False
        if name == "get_agenda":
            return _dump(_get_agenda(conn, args, now)), False
        if name == "save_agenda":
            return _dump(_save_agenda(conn, args, now)), False
        if name == "save_time_off":
            return _dump(_save_time_off(conn, args)), False
        _mark_reviewed(conn, now)
        return "ok", False
    except (QueryRejected, ValueError, LookupError) as e:
        return str(e), True
