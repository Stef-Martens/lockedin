"""What the coach can do: read the schema, run read-only SQL, read focus facts, and read or save goals."""

import json
from datetime import datetime

from fastapi.encoders import jsonable_encoder
from sqlalchemy import Connection, Engine, text

from lockedin.coach.sql import QueryRejected, run_readonly
from lockedin.focus.facts import focus_facts

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
  e1rm (estimated 1-rep max, Epley, kg). Dumbbell weights are as logged: see profile.dumbbell_weights.
exercises: id, name (Hevy's exercise name), is_bodyweight.
library_exercises: name, equipment ('barbell'|'dumbbell'|'cable'|'machine'|'bodyweight'|'other'), related_to, ratio.
library_muscles: exercise_name, muscle_key, role ('primary'|'secondary'). Join exercises.name = exercise_name.
muscles: key, name, region, target_low, target_high (weekly effective sets: primary = 1, secondary = 0.5).
measurement_types: id, name (Weight, Chest, Left arm, ...), unit ('kg' | 'cm'), kind ('weight'|'tape'|'other').
measurements: type_id, measured_on (date), value, note. One body check-in = all rows on one measured_on.
profile (single row): avoid_muscles (left-out muscle keys), never_exercises, coach_notes, date_of_birth, height_cm, sex, max_hr_override, ftp_override, resting_hr_override,
  dumbbell_weights ('pair' = logged weight is both dumbbells together, 'each' = per hand), reminder_weeks,
  last_goal_review_at.
goals: id, text, area, target, exercise (exact lift name, if about one), status ('active'|'achieved'|'dropped'),
  source, created_at, updated_at.

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
           "area": {"type": "string", "description": "bike, run, swim, gym, body or general."},
           "target": {"type": "string", "description": "When or how it's measured, e.g. 'by March 2027'."},
           "exercise": {"type": "string", "description": "Exact exercise name when the goal is about one lift, "
                        "e.g. 'Bench Press (Barbell)'."}},
          ["action"]),
    _tool("mark_goals_reviewed", "Record that the periodic goal check-in happened (the owner confirmed or changed "
          "their goals), so the next one is due in about 4 weeks."),
]
SCHEMAS = {t["name"]: t["input_schema"] for t in TOOLS}
TYPES = {"string": str, "integer": int, "object": dict}


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
        if not isinstance(value, TYPES[spec["type"]]) or isinstance(value, bool):
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
    if len(args.get("exercise", "")) > 120:
        raise ValueError("'exercise' must be an exercise name (at most 120 characters).")
    fields = {k: args[k].strip() or None for k in ("text", "area", "target", "exercise") if k in args}
    if action == "create":
        if not fields.get("text"):
            raise ValueError("'create' needs a non-empty text.")
        goal_id = conn.execute(text(
            "insert into goals (text, area, target, exercise, created_at, updated_at) "
            "values (:text, :area, :target, :exercise, :now, :now) returning id"),
            {"area": None, "target": None, "exercise": None, **fields, "now": now}).scalar_one()
    else:
        if "goal_id" not in args:
            raise ValueError(f"'{action}' needs goal_id.")
        if "text" in fields and not fields["text"]:
            raise ValueError("A goal's text can't be empty.")
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
            rows = conn.execute(text(f"select {GOAL_FIELDS} from goals order by created_at desc, id desc")).mappings()
            return _dump([dict(r) for r in rows]), False
        if name == "save_goal":
            return _dump(_save_goal(conn, args, now)), False
        _mark_reviewed(conn, now)
        return "ok", False
    except (QueryRejected, ValueError) as e:
        return str(e), True
