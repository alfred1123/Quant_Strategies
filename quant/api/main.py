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

from quant.api.auth.dependencies import require_user, require_user_or_service  # noqa: E402
from quant.api.auth.router import limiter as auth_limiter, router as auth_router  # noqa: E402
from quant.api.auth.service import AuthService  # noqa: E402
from quant.api.credentials.router import limiter as credentials_limiter, router as credentials_router  # noqa: E402
from quant.api.credentials.service import CredentialService  # noqa: E402
from quant.api.admin.router import router as admin_router  # noqa: E402
from quant.api.market_data.router import router as market_data_router  # noqa: E402
from quant.api.scheduler.router import router as scheduler_router  # noqa: E402
from quant.api.exception_handlers import register as register_exception_handlers  # noqa: E402
from quant.api.routers import backtest, config, deployments, inst, jobs, promotion, refdata, strategies  # noqa: E402
from quant.refdata.bundle import DataCaches  # noqa: E402
from quant.refdata.publisher import RefDataPublisher  # noqa: E402
from quant.shared.db import DbGateway, close_pools, open_pool  # noqa: E402

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: open the DB pool, publish REFDATA → Redis, build caches.

    Order matters: the publisher seeds ``refdata:<table>`` and ``config:<table>``
    so the bundle's ``RedisRefData`` reader (and the worker's) can resolve
    rows immediately. If Redis is unreachable, those endpoints will 503 but
    the server still boots so ``/health`` remains useful for diagnosis.
    """
    open_pool(DB_CONNINFO)
    try:
        app.state.auth_service = AuthService()
        app.state.db_conninfo = DB_CONNINFO

        from quant.shared.secrets_crypto import CredentialCrypto
        app.state.credential_crypto = CredentialCrypto()
        app.state.credential_service = CredentialService(app.state.credential_crypto)

        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        try:
            n = RefDataPublisher(DB_CONNINFO, redis_url).publish_all()
            logger.info("Published %d tables to Redis", n)
        except Exception:
            logger.exception(
                "RefDataPublisher.publish_all() failed — catalog and policy endpoints will 503 "
                "until POST /api/v1/refdata/refresh and POST /api/v1/config/refresh succeed",
            )

        caches = DataCaches(DB_CONNINFO, redis_url)
        caches.load_instruments(soft_fail=False)
        app.state.data_caches = caches

        from quant.trade.brokers.ccxt.routing import KeyRouter
        from quant.trade.registry import AdapterRegistry, build_default_registry

        try:
            app.state.adapter_registry = build_default_registry(
                caches.refdata, key_router=KeyRouter(caches.key_profiles)
            )
            logger.info("Adapter registry ready for ccxt brokers")
        except Exception:
            logger.exception(
                "Failed to build adapter registry — ccxt dry-run will reject unknown app_id",
            )
            app.state.adapter_registry = AdapterRegistry()

        from quant.trade.venue_limits import VenueLimitsPublisher

        try:
            n = VenueLimitsPublisher(redis_url, refdata=caches.refdata).publish_all()
            logger.info("Cached order-size limits for %d broker app(s)", n)
        except Exception:
            # One public load_markets per venue, so a slow or unreachable
            # exchange delays boot; it must never prevent it. Without a snapshot
            # a too-small qty is caught before the order instead of at edit time.
            logger.warning(
                "Venue order-size limits not cached — qty edits fall back to the "
                "pre-submit check. Retry with POST /api/v1/trade/venue-limits/refresh",
                exc_info=True,
            )

        from quant.trade.bar_source import PriceBarServiceFactory

        app.state.price_bars = PriceBarServiceFactory(DB_CONNINFO, caches)

        from quant.api.routers.deployments import build_trade_service
        from quant.queue.repo import BtQueueRepo
        from quant.trade.db_repo import TradeRepo
        from quant.trade.scheduler.sweep import DEFAULT_SETTLE_S, ScheduleSweeper
        from quant.trade.scheduler.tick import ScheduleTickRunner

        tick_bt = BtQueueRepo(DB_CONNINFO, user_id="system")
        app.state.schedule_sweeper = ScheduleSweeper(
            ScheduleTickRunner(
                TradeRepo(DB_CONNINFO, bt=tick_bt, user_id="system"),
                lambda app_user_id, deployment_id: build_trade_service(
                    app.state
                ).apply_deployment(app_user_id, deployment_id),
            ),
            caches.refdata,
            settle_s=DEFAULT_SETTLE_S,
        )

        yield
    finally:
        close_pools()


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
app.include_router(config.router, prefix="/api/v1", dependencies=[Depends(require_user)])
app.include_router(deployments.router, prefix="/api/v1", dependencies=[Depends(require_user)])
app.include_router(credentials_router, prefix="/api/v1", dependencies=[Depends(require_user)])
# The routers the scheduler Lambda drives, so their gates also admit the
# service token. Kept at router level so a new route cannot be added without a
# gate; a route needing a human specifically adds require_user itself.
app.include_router(admin_router, prefix="/api/v1", dependencies=[Depends(require_user_or_service)])
app.include_router(market_data_router, prefix="/api/v1", dependencies=[Depends(require_user_or_service)])
app.include_router(scheduler_router, prefix="/api/v1", dependencies=[Depends(require_user_or_service)])


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/health/ready")
def readiness(request: Request):
    """Liveness = /health.  Readiness = /health/ready (includes DB)."""
    try:
        DbGateway(request.app.state.db_conninfo).health_check()
        return {"status": "ok", "db": "connected"}
    except Exception as exc:
        logger.warning("Readiness check failed: %s", exc)
        return JSONResponse({"status": "degraded", "db": str(exc)}, status_code=503)
