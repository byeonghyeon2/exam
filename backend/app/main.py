import time
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.auth import admin_users, protected, public
from app.api.v1.router import router
from app.core.config import get_settings

settings = get_settings()
app = FastAPI(title=settings.app_name, debug=settings.app_debug)
app.add_middleware(CORSMiddleware, allow_origins=[settings.frontend_origin], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = request.headers.get("x-request-id", str(uuid4())); started = time.perf_counter()
    try: response = await call_next(request)
    except Exception:
        response = JSONResponse(status_code=500, content={"detail": "Internal server error", "request_id": request_id})
    response.headers["x-request-id"] = request_id; response.headers["x-response-time-ms"] = f"{(time.perf_counter()-started)*1000:.2f}"
    return response


app.include_router(public, prefix="/api/v1")
app.include_router(protected, prefix="/api/v1")
app.include_router(admin_users, prefix="/api/v1")
app.include_router(router, prefix="/api/v1")
