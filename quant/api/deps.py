"""FastAPI dependencies — application-scoped services from ``app.state``."""

from __future__ import annotations

from fastapi import Request

from quant.refdata.bundle import DataCaches


def get_data_caches(request: Request) -> DataCaches:
    """REFDATA (Redis) + INST + BT caches — built in ``quant.api.main`` lifespan."""
    return request.app.state.data_caches
