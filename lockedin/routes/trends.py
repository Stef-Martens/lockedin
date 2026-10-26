from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field
from sqlalchemy import Connection, text

from lockedin.auth import require_owner
from lockedin.db import get_conn
from lockedin.focus.coverage import muscle_coverage, unmapped_exercises
from lockedin.focus.musclemap import muscle_map
from lockedin.focus.sessions import counted
from lockedin.focus.suggest import gym_suggestions
from lockedin.focus.trends import bike_trends, gym_exercise_progress, gym_weekly_volume, run_trends, swim_trends
from lockedin.routes.overview import get_now

router = APIRouter(prefix="/api", dependencies=[Depends(require_owner)])

TRENDS = {"bike": bike_trends, "run": run_trends, "swim": swim_trends}


class MuscleTags(BaseModel):
    equipment: Literal["barbell", "dumbbell", "cable", "machine", "bodyweight", "other"]
    primary: list[str] = Field(min_length=1)
    secondary: list[str] = []


@router.get("/trends/{sport}")
def trends(sport: str, weeks: int = 26, conn: Connection = Depends(get_conn), now: datetime = Depends(get_now)) -> dict:
    if sport not in TRENDS:
        raise HTTPException(404, "No trends for that sport.")
    return jsonable_encoder(TRENDS[sport](conn, now, max(4, min(weeks, 104))))


@router.get("/muscles")
def muscles(conn: Connection = Depends(get_conn)) -> list[dict]:
    return [dict(r._mapping) for r in conn.execute(text("select * from muscles order by sort"))]


@router.get("/muscle-map")
def muscle_map_week(week: date | None = None, conn: Connection = Depends(get_conn),
                    now: datetime = Depends(get_now)) -> dict:
    return jsonable_encoder(muscle_map(conn, now, week))


@router.get("/gym/coverage")
def coverage(conn: Connection = Depends(get_conn), now: datetime = Depends(get_now)) -> dict:
    return jsonable_encoder({"coverage": muscle_coverage(conn, now), "unmapped": unmapped_exercises(conn, now)})


@router.get("/gym/suggestions")
def suggestions(limit: int = 20, conn: Connection = Depends(get_conn), now: datetime = Depends(get_now)) -> list[dict]:
    return jsonable_encoder(gym_suggestions(conn, now, max(1, min(limit, 20))))


@router.get("/gym/volume")
def volume(weeks: int = 26, conn: Connection = Depends(get_conn), now: datetime = Depends(get_now)) -> list[dict]:
    return jsonable_encoder(gym_weekly_volume(conn, now, max(1, min(weeks, 104))))


@router.get("/gym/exercises")
def exercises(conn: Connection = Depends(get_conn)) -> list[dict]:
    rows = conn.execute(text(
        "select e.id, e.name, count(distinct a.id) as sessions, max(a.start_at) as last_done, max(s.e1rm) as best_e1rm, "
        "coalesce((select json_agg(json_build_object('key', lm.muscle_key, 'role', lm.role) order by lm.role, lm.muscle_key) "
        "from library_muscles lm where lm.exercise_name = e.name), '[]'::json) as muscles "
        f"from exercises e join gym_sets s on s.exercise_id = e.id join activities a on a.id = s.workout_id and {counted('a')} "
        "group by e.id, e.name order by last_done desc"
    )).all()
    return jsonable_encoder([{**r._mapping, "best_e1rm": round(r.best_e1rm, 1) if r.best_e1rm else None,
                              "mapped": bool(r.muscles)} for r in rows])


@router.get("/gym/exercises/{exercise_id}")
def exercise_progress(exercise_id: int, conn: Connection = Depends(get_conn)) -> dict:
    p = gym_exercise_progress(conn, exercise_id)
    if p["exercise"] is None:
        raise HTTPException(404, "Exercise not found.")
    return jsonable_encoder(p)


@router.put("/gym/exercises/{exercise_id}/muscles")
def tag_exercise(exercise_id: int, body: MuscleTags, conn: Connection = Depends(get_conn)) -> dict:
    name = conn.execute(text("select name from exercises where id = :i"), {"i": exercise_id}).scalar()
    if name is None:
        raise HTTPException(404, "Exercise not found.")
    known = set(conn.execute(text("select key from muscles")).scalars())
    unknown = [m for m in body.primary + body.secondary if m not in known]
    if unknown:
        raise HTTPException(422, f"Unknown muscle(s): {', '.join(unknown)}")
    conn.execute(text(
        "insert into library_exercises (name, equipment, created_by) values (:n, :e, 'owner') "
        "on conflict (name) do update set equipment = excluded.equipment"
    ), {"n": name, "e": body.equipment})
    conn.execute(text("delete from library_muscles where exercise_name = :n"), {"n": name})
    roles = {m: "secondary" for m in body.secondary} | {m: "primary" for m in body.primary}
    for muscle, role in roles.items():
        conn.execute(text("insert into library_muscles (exercise_name, muscle_key, role) values (:n, :m, :r)"),
                     {"n": name, "m": muscle, "r": role})
    return {"name": name, "equipment": body.equipment, "muscles": [{"key": m, "role": r} for m, r in roles.items()]}
