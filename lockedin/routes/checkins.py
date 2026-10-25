import math
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import Connection, text

from lockedin.auth import require_owner
from lockedin.db import get_conn
from lockedin.reminders import calendar_ics
from lockedin.routes.overview import get_now
from lockedin.timeutil import TZ

router = APIRouter(prefix="/api", dependencies=[Depends(require_owner)])


class CheckIn(BaseModel):
    measured_on: date
    values: dict[int, float | None]


MAX_VALUE = 1000  # no body measurement in kg or cm gets near this; catches typos like 7840


@router.post("/checkins", status_code=201)
def save_checkin(body: CheckIn, conn: Connection = Depends(get_conn), now: datetime = Depends(get_now)) -> dict:
    if body.measured_on > now.astimezone(TZ).date():
        raise HTTPException(422, "That date is in the future.")
    values = {t: v for t, v in body.values.items() if v is not None and v > 0}
    if bad := [v for v in values.values() if not math.isfinite(v) or v >= MAX_VALUE]:
        raise HTTPException(422, f"That value looks wrong: {bad[0]}. Check for a typo.")
    values = {t: round(v, 2) for t, v in values.items()}
    if not values:
        raise HTTPException(422, "Fill in at least one measurement.")
    known = set(conn.execute(text("select id from measurement_types where id = any(:ids)"), {"ids": list(values)}).scalars())
    if missing := set(values) - known:
        raise HTTPException(404, f"Unknown measurement type(s): {', '.join(map(str, sorted(missing)))}")
    for type_id, value in values.items():
        # One value per type per day: saving the same check-in again replaces it.
        conn.execute(text("delete from measurements where type_id = :t and measured_on = :d"), {"t": type_id, "d": body.measured_on})
        conn.execute(text("insert into measurements (type_id, measured_on, value) values (:t, :d, :v)"),
                     {"t": type_id, "d": body.measured_on, "v": value})
    return {"measured_on": body.measured_on, "saved": len(values)}


@router.get("/checkins")
def list_checkins(conn: Connection = Depends(get_conn)) -> list[dict]:
    out: dict[date, dict] = {}
    for r in conn.execute(text("select measured_on, type_id, value from measurements order by measured_on desc, type_id")):
        out.setdefault(r.measured_on, {})[str(r.type_id)] = r.value
    return [{"measured_on": d, "values": v} for d, v in out.items()]


@router.delete("/checkins/{measured_on}", status_code=204)
def delete_checkin(measured_on: date, conn: Connection = Depends(get_conn)) -> Response:
    if not conn.execute(text("delete from measurements where measured_on = :d returning id"), {"d": measured_on}).first():
        raise HTTPException(404, "No check-in on that date.")
    return Response(status_code=204)


@router.get("/reminders/calendar.ics")
def calendar(request: Request, conn: Connection = Depends(get_conn), now=Depends(get_now)) -> Response:
    ics = calendar_ics(conn, now.astimezone(TZ).date(), str(request.base_url))
    return Response(ics, media_type="text/calendar; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="lockedin-checkin.ics"'})
