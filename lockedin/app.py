from fastapi import Depends, FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from lockedin.auth import require_owner
from lockedin.config import Settings, get_settings
from lockedin.routes import activities, agenda, body, checkins, coach, fit, forecast, hevy, overview, plan, preferences, status, timeoff, trends


def docs_urls(s: Settings) -> dict:
    """The API docs only on the local stack; in production they'd map the API for anyone."""
    local = s.is_local
    return {"docs_url": "/api/docs" if local else None, "redoc_url": None,
            "openapi_url": "/api/openapi.json" if local else None}


app = FastAPI(title="LockedIn", **docs_urls(get_settings()))


@app.exception_handler(RequestValidationError)
async def _plain_messages(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Our own validators' messages are written for people; drop pydantic's "Value error, " in front."""
    for err in exc.errors():
        if isinstance(err.get("msg"), str):
            err["msg"] = err["msg"].removeprefix("Value error, ")
    return await request_validation_exception_handler(request, exc)

app.include_router(fit.router)
app.include_router(hevy.router)
app.include_router(activities.router)
app.include_router(body.router)
app.include_router(status.router)
app.include_router(overview.router)
app.include_router(trends.router)
app.include_router(forecast.router)
app.include_router(checkins.router)
app.include_router(coach.router)
app.include_router(preferences.router)
app.include_router(plan.router)
app.include_router(agenda.sync_router)
app.include_router(agenda.router)
app.include_router(timeoff.router)


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
