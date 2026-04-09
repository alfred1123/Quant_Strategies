"""FastAPI application — backtest & REFDATA endpoints.

Run:
    cd <project_root>
    uvicorn api.main:app --reload --port 8000
"""

import logging
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Add src/ to import path so pipeline modules resolve
sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir, "src"))

from src.log_config import setup_logging  # noqa: E402
from api.services.refdata_cache import RefDataCache  # noqa: E402
from api.routers import backtest, refdata  # noqa: E402

logger = logging.getLogger(__name__)

DB_CONNINFO = os.getenv(
    "QUANTDB_CONNINFO",
    "host={host} port={port} dbname=quantdb user={user} password={password} sslmode=require".format(
        host=os.getenv("QUANTDB_HOST", "localhost"),
        port=os.getenv("QUANTDB_PORT", "5433"),
        user=os.getenv("QUANTDB_USERNAME", "quant_admin"),
        password=os.getenv("QUANTDB_PASSWORD", ""),
    ),
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: load REFDATA cache.  Shutdown: no-op."""
    setup_logging()
    cache = RefDataCache(DB_CONNINFO)
    try:
        cache.load_all()
    except Exception:
        logger.error("Failed to connect to REFDATA database — "
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
    allow_origins=["http://localhost:5173"],  # Vite dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(backtest.router, prefix="/api/v1")
app.include_router(refdata.router, prefix="/api/v1")


@app.get("/health")
def health():
    return {"status": "ok"}
