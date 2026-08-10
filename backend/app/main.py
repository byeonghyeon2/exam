import logging
import time
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.auth import admin_users, protected, public
from app.api.v1.router import router
from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)
LOCAL_ORIGIN_REGEX = r"https?://(?:localhost|127\.0\.0\.1|10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}|172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2})(?::\d+)?"


async def request_context(request: Request, call_next):
    request_id = request.headers.get("x-request-id", str(uuid4())); started = time.perf_counter()
    try: response = await call_next(request)
    except Exception:
        logger.exception("Unhandled request error", extra={"request_id": request_id})
        response = JSONResponse(status_code=500, content={"detail": "Internal server error", "request_id": request_id})
    response.headers["x-request-id"] = request_id; response.headers["x-response-time-ms"] = f"{(time.perf_counter()-started)*1000:.2f}"
    return response


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    application = FastAPI(title=settings.app_name, debug=settings.app_debug)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_origin_regex=LOCAL_ORIGIN_REGEX if settings.cors_allow_local_network else None,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.middleware("http")(request_context)
    application.include_router(public, prefix="/api/v1")
    application.include_router(protected, prefix="/api/v1")
    application.include_router(admin_users, prefix="/api/v1")
    application.include_router(router, prefix="/api/v1")
    return application


app = create_app()
