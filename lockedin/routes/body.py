from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import Connection, text
from sqlalchemy.exc import IntegrityError

from lockedin.auth import require_owner
from lockedin.db import get_conn
from lockedin.fitness import recompute_training_load

router = APIRouter(prefix="/api", dependencies=[Depends(require_owner)])

PROFILE_FIELDS = ("date_of_birth", "height_cm", "sex", "max_hr_override", "ftp_override", "resting_hr_override",
                  "dumbbell_weights", "reminder_weeks", "reminder_hevy")


class Profile(BaseModel):
    date_of_birth: date | None = None
    height_cm: float | None = Field(None, ge=100, le=250)
    sex: Literal["male", "female"] | None = None
    max_hr_override: int | None = Field(None, ge=120, le=230)
    ftp_override: int | None = Field(None, ge=50, le=600)
    resting_hr_override: int | None = Field(None, ge=30, le=110)
    dumbbell_weights: Literal["pair", "each"] = "pair"
    reminder_weeks: Literal[1, 2, 4] = 2
    reminder_hevy: bool = True


class MeasurementType(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    unit: str = Field(min_length=1, max_length=10)
    kind: Literal["weight", "tape", "other"]


class Measurement(BaseModel):
    type_id: int
    measured_on: date
    value: float = Field(gt=0, lt=1000)
    note: str | None = Field(None, max_length=200)


@router.get("/profile")
def get_profile(conn: Connection = Depends(get_conn)) -> dict:
    row = conn.execute(text(f"select {', '.join(PROFILE_FIELDS)} from profile where id = 1")).one()
    return dict(row._mapping)


@router.put("/profile")
def put_profile(body: Profile, conn: Connection = Depends(get_conn)) -> dict:
    sets = ", ".join(f"{f} = :{f}" for f in PROFILE_FIELDS)
    before = conn.execute(text("select ftp_override from profile where id = 1")).scalar()
    conn.execute(text(f"update profile set {sets}, updated_at = now() where id = 1"), body.model_dump())
    if body.ftp_override != before:
        recompute_training_load(conn)
    return get_profile(conn)


@router.get("/measurement-types")
def list_types(conn: Connection = Depends(get_conn)) -> list[dict]:
    return [dict(r._mapping) for r in conn.execute(text("select id, name, unit, kind from measurement_types order by id"))]


@router.post("/measurement-types", status_code=201)
def add_type(body: MeasurementType, conn: Connection = Depends(get_conn)) -> dict:
    name = body.name.strip()
    if conn.execute(text("select 1 from measurement_types where lower(name) = lower(:n)"), {"n": name}).first():
        raise HTTPException(409, f"There is already a measurement called {name!r}.")
    try:
        row = conn.execute(text("insert into measurement_types (name, unit, kind) values (:n, :u, :k) "
                                "returning id, name, unit, kind"), {"n": name, "u": body.unit.strip(), "k": body.kind}).one()
    except IntegrityError:
        raise HTTPException(409, f"There is already a measurement called {name!r}.") from None
    return dict(row._mapping)


@router.get("/measurements")
def list_measurements(type_id: int | None = None, conn: Connection = Depends(get_conn)) -> list[dict]:
    rows = conn.execute(text(
        "select id, type_id, measured_on, value, source, note from measurements "
        "where (cast(:t as bigint) is null or type_id = :t) order by measured_on, id"
    ), {"t": type_id})
    return [dict(r._mapping) for r in rows]


@router.post("/measurements", status_code=201)
def add_measurement(body: Measurement, conn: Connection = Depends(get_conn)) -> dict:
    if not conn.execute(text("select 1 from measurement_types where id = :t"), {"t": body.type_id}).first():
        raise HTTPException(404, "Unknown measurement type.")
    row = conn.execute(text(
        "insert into measurements (type_id, measured_on, value, note) values (:type_id, :measured_on, :value, :note) "
        "returning id, type_id, measured_on, value, source, note"
    ), body.model_dump()).one()
    return dict(row._mapping)


@router.delete("/measurements/{measurement_id}", status_code=204)
def delete_measurement(measurement_id: int, conn: Connection = Depends(get_conn)) -> Response:
    if not conn.execute(text("delete from measurements where id = :i returning id"), {"i": measurement_id}).first():
        raise HTTPException(404, "Measurement not found.")
    return Response(status_code=204)
