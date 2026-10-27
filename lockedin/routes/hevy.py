from dataclasses import asdict

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import Connection

from lockedin.auth import require_owner
from lockedin.config import get_settings
from lockedin.db import get_conn
from lockedin.hevy.importer import import_hevy
from lockedin.hevy.parse import parse_hevy_csv

router = APIRouter(prefix="/api/hevy", dependencies=[Depends(require_owner)])


@router.post("/upload")
async def upload(file: UploadFile = File(...), conn: Connection = Depends(get_conn)) -> dict:
    limit = get_settings().max_upload_bytes
    data = await file.read(limit + 1)  # Content-Length is checked up front, but may be missing or wrong
    if len(data) > limit:
        raise HTTPException(413, f"File too large (max {limit // 1_000_000} MB).")
    try:
        parsed = parse_hevy_csv(data.decode("utf-8"))
    except UnicodeDecodeError:
        raise HTTPException(422, "This doesn't look like a CSV file. Export it from Hevy and try again.") from None
    except ValueError as e:
        raise HTTPException(422, str(e)) from None
    return asdict(import_hevy(conn, parsed))
