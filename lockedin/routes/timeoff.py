from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import Connection

from lockedin import timeoff
from lockedin.agenda.store import local_today
from lockedin.auth import require_owner
from lockedin.db import get_conn
from lockedin.routes.overview import get_now

router = APIRouter(prefix="/api", dependencies=[Depends(require_owner)])


@router.get("/time-off")
def list_time_off(conn: Connection = Depends(get_conn), now: datetime = Depends(get_now)) -> list[dict]:
    """Time off that is under way or still to come."""
    return timeoff.entries(conn, since=local_today(now))


@router.post("/time-off", status_code=201)
def add(body: timeoff.TimeOffIn, conn: Connection = Depends(get_conn)) -> dict:
    return timeoff.create(conn, body)


@router.patch("/time-off/{entry_id}")
def edit(entry_id: int, body: timeoff.TimeOffIn, conn: Connection = Depends(get_conn)) -> dict:
    try:
        return timeoff.update(conn, entry_id, body)
    except LookupError as e:
        raise HTTPException(404, str(e)) from None


@router.delete("/time-off/{entry_id}", status_code=204)
def remove(entry_id: int, conn: Connection = Depends(get_conn)) -> Response:
    try:
        timeoff.delete(conn, entry_id)
    except LookupError as e:
        raise HTTPException(404, str(e)) from None
    return Response(status_code=204)
