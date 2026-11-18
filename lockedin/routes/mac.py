"""The Mac sync's check-ins: every full run is reported, and a "Check again" from the site waits here until the
Mac's once-a-minute poll picks it up. The site never reaches the Mac; the Mac always calls in."""

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import Connection, text

from lockedin.auth import require_owner, require_sync
from lockedin.db import get_conn

sync_router = APIRouter(prefix="/api/sync/mac", dependencies=[Depends(require_sync)])
router = APIRouter(prefix="/api/sync/mac", dependencies=[Depends(require_owner)])

FIELDS = ("last_run_at", "last_seen_at", "last_run_uploaded", "last_run_errors",
          "check_requested_at", "check_done_at", "check_uploaded")


def mac_status(conn: Connection) -> dict:
    row = conn.execute(text(f"select {', '.join(FIELDS)} from mac_sync where id = 1")).mappings().first()
    return dict(row) if row else dict.fromkeys(FIELDS)


class RunReport(BaseModel):
    uploaded: int = Field(ge=0)
    errors: int = Field(ge=0)
    answered: datetime | None = None  # the check_requested_at this run answers


@sync_router.post("/poll")
def poll(conn: Connection = Depends(get_conn)) -> dict:
    """The Mac is awake; it gets the open request, if there is one."""
    requested = conn.execute(text(
        "update mac_sync set last_seen_at = now() where id = 1 returning "
        "case when check_requested_at is not null and (check_done_at is null or check_done_at < check_requested_at) "
        "then check_requested_at end"
    )).scalar()
    return {"check_requested_at": requested}


@sync_router.post("/run")
def run(body: RunReport, conn: Connection = Depends(get_conn)) -> dict:
    """A full run. It closes the request only if it answers the current one, so a press made during a check
    stays open for the next poll."""
    conn.execute(text(
        "update mac_sync set last_run_at = now(), last_seen_at = now(), "
        "last_run_uploaded = :up, last_run_errors = :err, "
        "check_done_at = case when check_requested_at = :answered then now() else check_done_at end, "
        "check_uploaded = case when check_requested_at = :answered then :up else check_uploaded end "
        "where id = 1"
    ), {"up": body.uploaded, "err": body.errors, "answered": body.answered})
    return {"ok": True}


@router.post("/check")
def check(conn: Connection = Depends(get_conn)) -> dict:
    """Ask the Mac to look again: nudge iCloud, rescan, upload. It answers at its next poll."""
    conn.execute(text("update mac_sync set check_requested_at = clock_timestamp() where id = 1"))
    return mac_status(conn)
