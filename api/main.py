"""FastAPI application — backtest & REFDATA endpoints.

Run:
    cd <project_root>
    uvicorn api.main:app --reload --port 8000
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.config import load_config

# load_config() initialises logging, loads .env or SSM, and returns the DB conninfo
DB_CONNINFO = load_config()

from api.services.refdata_cache import RefDataCache  # noqa: E402
from api.routers import backtest, refdata  # noqa: E402

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: load REFDATA cache.  Shutdown: no-op."""
    cache = RefDataCache(DB_CONNINFO)
    try:
        cache.load_all()
    except Exception:
        logger.exception("Failed to connect to REFDATA database — "
                         "server will start but REFDATA endpoints will be empty")
    app.state.refdata_cache = cache
    yield


app = FastAPI(
    title="Quant Backtest API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(backtest.router, prefix="/api/v1")
app.include_router(refdata.router, prefix="/api/v1")


@app.get("/health")
def health():
    return {"status": "ok"}
