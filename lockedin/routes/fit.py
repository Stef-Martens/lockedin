from dataclasses import asdict
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import Connection

from lockedin.auth import require_owner_or_sync
from lockedin.config import get_settings
from lockedin.db import get_conn
from lockedin.fit.importer import import_fit, known_hashes

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
