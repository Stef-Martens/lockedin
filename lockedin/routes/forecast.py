from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import Connection

from lockedin.auth import require_owner
from lockedin.db import get_conn
from lockedin.forecast import forecast
from lockedin.routes.overview import get_now

router = APIRouter(prefix="/api", dependencies=[Depends(require_owner)])


@router.get("/forecast")
def get_forecast(conn: Connection = Depends(get_conn), now: datetime = Depends(get_now)) -> dict:
    return forecast(conn, now)
