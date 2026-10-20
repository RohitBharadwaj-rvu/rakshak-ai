"""
app/main.py - GuardianLine FastAPI Backend Application Entrypoint (Lane B).

Mounts:
  - GET  /health
  - POST /tools/classify_caller        (Lane D engine + Lane B timeout wrapper)
  - GET  /tools/classify_caller/health
  - POST /tools/switch_to_honeypot     (Lane B mid-call persona & bait tool)
  - POST /tools/log_intel              (Lane B mid-call intel logging tool)
  - POST /webhook                      (Lane B Bolna post-call webhook -> SQLite CallRecord)
  - GET  /api/calls                    (Lane B CallRecord list API)
  - GET  /api/calls/{call_id}          (Lane B CallRecord detail API)
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.classifier_router import router as classifier_router
from app.core.lane_c import install as install_lane_c
from app.voice.store import init_db
from app.voice.tools import router as tools_router
from app.voice.webhook import router as webhook_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("GuardianLine Backend initialized (SQLite store ready).")
    yield


app = FastAPI(
    title="GuardianLine Backend",
    description="Real-time voice screening, elderly honeypot tools, and intelligence extraction API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(classifier_router)
app.include_router(tools_router)
app.include_router(webhook_router)
install_lane_c(app)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Return HTTP 422 naming any missing or invalid fields, with zero stack traces (T-CONTRACT, T-TOOLS).
    """
    missing_fields = []
    for err in exc.errors():
        loc = err.get("loc", ())
        if loc:
            missing_fields.append(str(loc[-1]))
    detail_msg = (
        f"Validation failed for field(s): {', '.join(missing_fields)}"
        if missing_fields
        else "Validation error"
    )
    from fastapi.encoders import jsonable_encoder
    return JSONResponse(
        status_code=422,
        content={
            "detail": detail_msg,
            "fields": missing_fields,
            "errors": jsonable_encoder(exc.errors()),
        },
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Ensure no response ever leaks a raw stack trace (T-TOOLS)."""
    logger.error("Unhandled error on %s %s: %s", request.method, request.url.path, type(exc).__name__)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "error_type": type(exc).__name__,
        },
    )


@app.api_route("/", methods=["GET", "HEAD"], tags=["Health"])
@app.api_route("/health", methods=["GET", "HEAD"], tags=["Health"])
async def health_check():
    """Public smoke check endpoint (T-HOST)."""
    return {
        "status": "ok",
        "service": "guardianline-backend",
    }
