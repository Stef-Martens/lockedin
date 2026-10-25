from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse

from lockedin.auth import require_owner
from lockedin.config import get_settings
from lockedin.routes import activities, body, checkins, fit, hevy, overview, status, trends

app = FastAPI(title="LockedIn", docs_url="/api/docs", openapi_url="/api/openapi.json")
app.include_router(fit.router)
app.include_router(hevy.router)
app.include_router(activities.router)
app.include_router(body.router)
app.include_router(status.router)
app.include_router(overview.router)
app.include_router(trends.router)
app.include_router(checkins.router)


@app.middleware("http")
async def limit_body_size(request: Request, call_next):
    length = request.headers.get("content-length")
    if length and length.isdigit() and int(length) > get_settings().max_upload_bytes:
        return JSONResponse({"detail": "File too large (max 4 MB)."}, status_code=413)
    return await call_next(request)


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


@app.get("/api/me")
def me(email: str = Depends(require_owner)) -> dict:
    return {"email": email}
