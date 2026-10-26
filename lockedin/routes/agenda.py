from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import Connection

from fastapi.encoders import jsonable_encoder

from lockedin.agenda import store
from lockedin.agenda.detail import detail
from lockedin.auth import require_owner, require_sync
from lockedin.db import get_conn
from lockedin.routes.overview import get_now

router = APIRouter(prefix="/api/agenda", dependencies=[Depends(require_owner)])
sync_router = APIRouter(prefix="/api/agenda", dependencies=[Depends(require_sync)])


def _problem(e: Exception) -> HTTPException:
    if isinstance(e, LookupError):
        return HTTPException(404, str(e))
    if isinstance(e, ValidationError):
        return HTTPException(422, "; ".join(err["msg"].removeprefix("Value error, ") for err in e.errors()))
    return HTTPException(422, str(e))


@router.get("")
def get_week(week: date | None = None, conn: Connection = Depends(get_conn), now: datetime = Depends(get_now)) -> dict:
    return store.week(conn, now, week)


@router.get("/{item_id}/detail")
def item_detail(item_id: int, conn: Connection = Depends(get_conn), now: datetime = Depends(get_now)) -> dict:
    try:
        return jsonable_encoder(detail(conn, now, item_id))
    except LookupError as e:
        raise _problem(e) from None


@router.post("", status_code=201)
def add(item: store.ItemIn, conn: Connection = Depends(get_conn), now: datetime = Depends(get_now)) -> dict:
    try:
        return store.create(conn, now, item, "manual")
    except ValueError as e:
        raise _problem(e) from None


@router.patch("/{item_id}")
def edit(item_id: int, patch: store.ItemPatch, conn: Connection = Depends(get_conn),
         now: datetime = Depends(get_now)) -> dict:
    try:
        return store.update(conn, now, item_id, patch)
    except (ValueError, LookupError) as e:
        raise _problem(e) from None


@router.delete("/{item_id}", status_code=204)
def remove(item_id: int, conn: Connection = Depends(get_conn)) -> Response:
    try:
        store.delete(conn, item_id)
    except LookupError as e:
        raise _problem(e) from None
    return Response(status_code=204)


@sync_router.post("/zwift/sync")
def zwift_sync(conn: Connection = Depends(get_conn), now: datetime = Depends(get_now)) -> list[dict]:
    return store.zwift_feed(conn, now)


class Confirmed(BaseModel):
    item_ids: list[int] = Field(default_factory=list, max_length=500)


@sync_router.post("/zwift/confirm")
def zwift_confirm(body: Confirmed, conn: Connection = Depends(get_conn), now: datetime = Depends(get_now)) -> dict:
    return {"confirmed": store.confirm_in_zwift(conn, now, body.item_ids)}
