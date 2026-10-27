from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import Connection

from lockedin.auth import require_owner_or_watch
from lockedin.db import get_conn
from lockedin.routes.overview import get_now
from lockedin.watch import feed

router = APIRouter(prefix="/api/watch", dependencies=[Depends(require_owner_or_watch)])


@router.get("/runs")
def runs(conn: Connection = Depends(get_conn), now: datetime = Depends(get_now)) -> dict:
    return feed(conn, now)
