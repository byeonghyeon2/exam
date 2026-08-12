import logging
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.auth import admin_users, protected, public
from app.api.v1.router import router
from app.core.config import Settings, get_settings
from app.core.http_security import FixedWindowRateLimiter, is_problem_data_request, rate_limit_keys
from app.services.auth import revoke_active_sessions

logger = logging.getLogger(__name__)
LOCAL_ORIGIN_REGEX = r"https?://(?:localhost|127\.0\.0\.1|10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}|172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2})(?::\d+)?"


def secure_api_response(request: Request, response: Response) -> Response:
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    return response


async def request_context(request: Request, call_next):
    request_id = request.headers.get("x-request-id", str(uuid4())); started = time.perf_counter()
    try: response = await call_next(request)
    except Exception:
        logger.exception("Unhandled request error", extra={"request_id": request_id})
        response = JSONResponse(status_code=500, content={"detail": "Internal server error", "request_id": request_id})
    response.headers["x-request-id"] = request_id; response.headers["x-response-time-ms"] = f"{(time.perf_counter()-started)*1000:.2f}"
    return secure_api_response(request, response)


def create_app(
    settings: Settings | None = None,
    session_revoker: Callable[[], int] | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    production = settings.app_env.strip().lower() == "production"

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        if (
            settings.auth_required
            and session_revoker is not None
            and not getattr(application.state, "disable_startup_session_revocation", False)
        ):
            revoked_count = session_revoker()
            logger.info("Revoked active authentication sessions on startup", extra={"revoked_count": revoked_count})
        yield

    application = FastAPI(
        title=settings.app_name,
        debug=settings.app_debug and not production,
        docs_url=None if production else "/docs",
        redoc_url=None if production else "/redoc",
        openapi_url=None if production else "/openapi.json",
        lifespan=lifespan,
    )
    limiter = FixedWindowRateLimiter(
        settings.question_rate_limit_requests,
        settings.question_rate_limit_window_seconds,
    )

    @application.middleware("http")
    async def protect_problem_data(request: Request, call_next):
        if is_problem_data_request(request):
            for key in rate_limit_keys(request, settings.proxy_trusted_ips):
                allowed, retry_after = limiter.consume(key)
                if not allowed:
                    return secure_api_response(request, JSONResponse(
                        status_code=429,
                        content={"detail": "Too many problem-data requests"},
                        headers={"Retry-After": str(retry_after)},
                    ))
        response = await call_next(request)
        return secure_api_response(request, response)
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


app = create_app(session_revoker=revoke_active_sessions)
