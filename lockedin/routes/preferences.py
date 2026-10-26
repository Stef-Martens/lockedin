from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Connection, text

from lockedin.auth import require_owner
from lockedin.db import get_conn
from lockedin.focus.preferences import load_preferences

router = APIRouter(prefix="/api", dependencies=[Depends(require_owner)])


class PreferencesBody(BaseModel):
    avoid_muscles: list[str] = Field(default_factory=list, max_length=20)
    never_exercises: list[str] = Field(default_factory=list, max_length=200)
    coach_notes: str = Field("", max_length=1000)


def _dedupe(names: list[str]) -> list[str]:
    out: list[str] = []
    for n in (n.strip() for n in names):
        if n and n not in out:
            out.append(n)
    return out


@router.get("/preferences")
def get_preferences(conn: Connection = Depends(get_conn)) -> dict:
    p = load_preferences(conn)
    return {"avoid_muscles": p.avoid_muscles, "never_exercises": p.never_exercises, "coach_notes": p.coach_notes}


@router.put("/preferences")
def put_preferences(body: PreferencesBody, conn: Connection = Depends(get_conn)) -> dict:
    known = set(conn.execute(text("select key from muscles")).scalars())
    avoid = _dedupe(body.avoid_muscles)
    unknown = [m for m in avoid if m not in known]
    if unknown:
        raise HTTPException(422, f"Unknown muscle: {', '.join(unknown)}")
    conn.execute(text("update profile set avoid_muscles = :a, never_exercises = :n, coach_notes = :c, "
                      "updated_at = now() where id = 1"),
                 {"a": avoid, "n": _dedupe(body.never_exercises), "c": body.coach_notes.strip()})
    return get_preferences(conn)
