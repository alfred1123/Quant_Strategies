"""FastAPI application — backtest & REFDATA endpoints.

Run:
    cd <project_root>
    uvicorn api.main:app --reload --port 8000
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from api.config import load_config

# load_config() initialises logging, loads .env or SSM, and returns the DB conninfo
DB_CONNINFO = load_config()

from api.auth.dependencies import require_user  # noqa: E402
from api.auth.router import limiter as auth_limiter, router as auth_router  # noqa: E402
from api.auth.service import AuthService  # noqa: E402
from api.routers import backtest, inst, refdata  # noqa: E402
from src.data import BacktestCache, InstrumentCache, RefDataCache  # noqa: E402

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: load REFDATA cache + BacktestCache.  Shutdown: no-op."""
    # Build the AuthService first so a missing JWT_SECRET fails the boot.
    app.state.auth_service = AuthService()
    app.state.db_conninfo = DB_CONNINFO
    cache = RefDataCache(DB_CONNINFO)
    try:
        cache.load_all()
    except Exception:
        logger.exception("Failed to connect to REFDATA database — "
                         "server will start but REFDATA endpoints will be empty")
    app.state.refdata_cache = cache
    app.state.backtest_cache = BacktestCache(DB_CONNINFO, refdata=cache)
    inst = InstrumentCache(DB_CONNINFO)
    try:
        inst.load_all()
    except Exception:
        logger.exception("Failed to load INST data — product endpoints will be empty")
    app.state.instrument_cache = inst
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api/v1")
app.include_router(backtest.router, prefix="/api/v1", dependencies=[Depends(require_user)])
app.include_router(inst.router, prefix="/api/v1", dependencies=[Depends(require_user)])
app.include_router(refdata.router, prefix="/api/v1", dependencies=[Depends(require_user)])


@app.get("/health")
def health():
    return {"status": "ok"}
