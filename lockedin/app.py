from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from lockedin.config import get_settings

app = FastAPI(title="LockedIn", docs_url="/api/docs", openapi_url="/api/openapi.json")


@app.middleware("http")
async def limit_body_size(request: Request, call_next):
    length = request.headers.get("content-length")
    if length and length.isdigit() and int(length) > get_settings().max_upload_bytes:
        return JSONResponse({"detail": "File too large (max 4 MB)."}, status_code=413)
    return await call_next(request)


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}
