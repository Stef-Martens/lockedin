from fastapi import APIRouter, Depends
from sqlalchemy import Connection, text

from lockedin.auth import require_owner
from lockedin.db import get_conn

router = APIRouter(prefix="/api", dependencies=[Depends(require_owner)])

SOURCES = ("zwift", "healthfit", "hevy")


@router.get("/status")
def status(conn: Connection = Depends(get_conn)) -> dict:
    out: dict = {}
    for src in SOURCES:
        out[src] = {
            "last_import_at": conn.execute(text("select max(at) from import_log where source = :s"), {"s": src}).scalar(),
            "count": conn.execute(text("select count(*) from activities where source = :s"), {"s": src}).scalar(),
        }
    out["last_tape_measurement_on"] = conn.execute(text(
        "select max(m.measured_on) from measurements m join measurement_types t on t.id = m.type_id where t.kind = 'tape'"
    )).scalar()
    return out
