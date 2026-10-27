from dataclasses import asdict
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import Connection

from lockedin.auth import require_owner_or_sync
from lockedin.config import get_settings
from lockedin.db import get_conn
from lockedin.fit.importer import import_fit, known_hashes
from lockedin.fitness import record_zwift_ftp
from lockedin.timeutil import TZ

router = APIRouter(prefix="/api/fit", dependencies=[Depends(require_owner_or_sync)])


class KnownRequest(BaseModel):
    hashes: list[str] = Field(max_length=500)


@router.post("/known")
def known(body: KnownRequest, conn: Connection = Depends(get_conn)) -> dict:
    found = known_hashes(conn, body.hashes)
    return {"known": [h for h in body.hashes if h in found]}


@router.post("/upload")
async def upload(file: UploadFile = File(...), source: Literal["zwift", "healthfit"] | None = Form(None),
                 conn: Connection = Depends(get_conn)) -> dict:
    limit = get_settings().max_upload_bytes
    data = await file.read(limit + 1)  # Content-Length is checked up front, but may be missing or wrong
    if len(data) > limit:
        raise HTTPException(413, f"File too large (max {limit // 1_000_000} MB).")
    return asdict(import_fit(conn, data, file.filename or "upload.fit", source))


class ZwiftFtpReading(BaseModel):
    at: datetime
    ftp: int = Field(ge=50, le=600)


class ZwiftFtpReadings(BaseModel):
    readings: list[ZwiftFtpReading] = Field(max_length=500)


@router.post("/zwift-ftp")
def zwift_ftp(body: ZwiftFtpReadings, conn: Connection = Depends(get_conn)) -> dict:
    """Zwift's FTP as the Mac sync found it in Zwift's logs; the last reading of a day stands for that day."""
    by_day: dict = {}
    for r in sorted(body.readings, key=lambda r: r.at):
        by_day[r.at.astimezone(TZ).date()] = r.ftp
    return {"recorded": sum(record_zwift_ftp(conn, day, ftp) for day, ftp in sorted(by_day.items()))}
