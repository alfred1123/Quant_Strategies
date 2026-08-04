"""FastAPI application — backtest & REFDATA endpoints.

Run:
    cd <project_root>
    uvicorn quant.api.main:app --reload --port 8000
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from quant.shared.config import load_config

# load_config() initialises logging, loads .env or SSM, and returns the DB conninfo
DB_CONNINFO = load_config()

from quant.api.auth.dependencies import require_user  # noqa: E402
from quant.api.auth.router import limiter as auth_limiter, router as auth_router  # noqa: E402
from quant.api.auth.service import AuthService  # noqa: E402
from quant.api.credentials.router import limiter as credentials_limiter, router as credentials_router  # noqa: E402
from quant.api.credentials.service import CredentialService  # noqa: E402
from quant.api.admin.router import router as admin_router  # noqa: E402
from quant.api.exception_handlers import register as register_exception_handlers  # noqa: E402
from quant.api.routers import backtest, deployments, inst, jobs, promotion, refdata, strategies  # noqa: E402
from quant.refdata.bundle import DataCaches  # noqa: E402
from quant.refdata.publisher import RefDataPublisher  # noqa: E402

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: publish REFDATA → Redis, then build DataCaches bundle.

    Order matters: the publisher seeds ``refdata:<table>`` keys from
    Postgres so the bundle's ``RedisRefData`` reader (and the worker's)
    can resolve enums immediately. If Redis is unreachable, REFDATA
    endpoints will 503 but the server still boots so ``/health`` remains
    useful for diagnosis.
    """
    # Build singletons — missing secrets fail the boot in prod.
    app.state.auth_service = AuthService()
    app.state.db_conninfo = DB_CONNINFO

    from quant.shared.secrets_crypto import CredentialCrypto
    app.state.credential_crypto = CredentialCrypto()
    app.state.credential_service = CredentialService(app.state.credential_crypto)

    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    try:
        n = RefDataPublisher(DB_CONNINFO, redis_url).publish_all()
        logger.info("Published %d REFDATA tables to Redis", n)
    except Exception:
        logger.exception(
            "RefDataPublisher.publish_all() failed — REFDATA endpoints will 503 "
            "until POST /api/v1/refdata/refresh succeeds",
        )

    caches = DataCaches(DB_CONNINFO, redis_url)
    caches.load_instruments(soft_fail=False)
    app.state.data_caches = caches

    from quant.trade.registry import AdapterRegistry, build_default_registry

    try:
        app.state.adapter_registry = build_default_registry(caches.refdata)
        logger.info("Adapter registry ready for ccxt brokers")
    except Exception:
        logger.exception(
            "Failed to build adapter registry — ccxt dry-run will reject unknown app_id",
        )
        app.state.adapter_registry = AdapterRegistry()

    # Application-scoped: holds a long-lived PriceBarRepo connection and caches
    # a ccxt client per venue, so it must outlive the per-request TradeService.
    from quant.trade.bar_source import PriceBarServiceFactory

    app.state.price_bars = PriceBarServiceFactory(DB_CONNINFO, caches)

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
app.state.credentials_limiter = credentials_limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
register_exception_handlers(app)

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
app.include_router(jobs.router, prefix="/api/v1", dependencies=[Depends(require_user)])
app.include_router(strategies.router, prefix="/api/v1", dependencies=[Depends(require_user)])
app.include_router(promotion.router, prefix="/api/v1", dependencies=[Depends(require_user)])
app.include_router(refdata.router, prefix="/api/v1", dependencies=[Depends(require_user)])
app.include_router(deployments.router, prefix="/api/v1", dependencies=[Depends(require_user)])
app.include_router(credentials_router, prefix="/api/v1", dependencies=[Depends(require_user)])
app.include_router(admin_router, prefix="/api/v1", dependencies=[Depends(require_user)])


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/health/ready")
def readiness(request: Request):
    """Liveness = /health.  Readiness = /health/ready (includes DB)."""
    import psycopg
    try:
        with psycopg.connect(request.app.state.db_conninfo, connect_timeout=3) as conn:
            conn.execute("SELECT 1")
        return {"status": "ok", "db": "connected"}
    except Exception as exc:
        logger.warning("Readiness check failed: %s", exc)
        return JSONResponse({"status": "degraded", "db": str(exc)}, status_code=503)
