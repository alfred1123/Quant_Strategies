"""FastAPI application — backtest & REFDATA endpoints.

Run:
    cd <project_root>
    uvicorn api.main:app --reload --port 8000
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from api.config import get_redis_url, load_config

# load_config() initialises logging, loads .env or SSM, and returns the DB conninfo
DB_CONNINFO = load_config()

from api.auth.dependencies import require_user  # noqa: E402
from api.auth.router import limiter as auth_limiter, router as auth_router  # noqa: E402
from api.auth.service import AuthService  # noqa: E402
from api.routers import backtest, inst, jobs, refdata  # noqa: E402
from quant.refdata.bundle import DataCaches  # noqa: E402
from quant.refdata.publisher import RefDataPublisher  # noqa: E402

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: publish REFDATA → Redis, build caches, load INST.

    FastAPI now owns REFDATA publishing (previously the TS coordinator).
    Publish is best-effort at boot: if Redis or Postgres is unreachable
    we log a warning and continue so /health stays useful and the admin
    can call ``POST /api/v1/refdata/refresh`` once the dependency is back.
    """
    # Build the AuthService first so a missing JWT_SECRET fails the boot.
    app.state.auth_service = AuthService()
    app.state.db_conninfo = DB_CONNINFO
    redis_url = get_redis_url()
    try:
        n = RefDataPublisher(DB_CONNINFO, redis_url).publish_all()
        logger.info("REFDATA boot publish: %d tables → %s", n, redis_url)
    except Exception:
        logger.warning(
            "REFDATA boot publish failed — endpoints will 503 until POST /api/v1/refdata/refresh succeeds",
            exc_info=True,
        )
    caches = DataCaches(DB_CONNINFO, redis_url)
    if not caches.refdata.ping():
        logger.warning("REFDATA Redis at %s is not reachable", redis_url)
    app.state.data_caches = caches
    app.state.refdata_cache = caches.refdata
    app.state.backtest_cache = caches.backtest_cache
    caches.load_instruments(soft_fail=False)
    app.state.instrument_cache = caches.instrument_cache
    yield


_is_prod = os.getenv("APP_ENV", "dev").lower() == "prod"

app = FastAPI(
    title="Quant Backtest API",
    version="0.1.0",
    lifespan=lifespan,
    docs_url=None if _is_prod else "/docs",
    redoc_url=None if _is_prod else "/redoc",
    openapi_url=None if _is_prod else "/openapi.json",
)

# slowapi: per-route rate limits (e.g. /auth/login). The limiter instance is
# shared with api.auth.router so its @limiter.limit decorators take effect.
app.state.limiter = auth_limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
# Inner middleware — CORS is added after this so CORS runs first for browser preflight.
app.add_middleware(SlowAPIMiddleware)

# CORS: comma-separated origins from CORS_ORIGINS only (SSM / .env). Empty =
# no cross-origin allowances; same-origin requests (e.g. Vite /api proxy) are
# unaffected by this list.
_cors_list = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api/v1")
app.include_router(backtest.router, prefix="/api/v1", dependencies=[Depends(require_user)])
app.include_router(inst.router, prefix="/api/v1", dependencies=[Depends(require_user)])
app.include_router(jobs.router, prefix="/api/v1", dependencies=[Depends(require_user)])
app.include_router(refdata.router, prefix="/api/v1", dependencies=[Depends(require_user)])


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/health/ready")
def readiness(request: Request):
    """Liveness = /health.  Readiness = /health/ready (includes DB)."""
    from quant.shared.db import DbGateway
    try:
        DbGateway(request.app.state.db_conninfo).health_check(timeout=3)
        return {"status": "ok", "db": "connected"}
    except Exception as exc:
        logger.warning("Readiness check failed: %s", exc)
        return JSONResponse({"status": "degraded", "db": str(exc)}, status_code=503)
