"""App-wide exception handlers — map domain/infra errors to HTTP responses."""

import logging

import psycopg
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from quant.market_data.fetcher import BarFetchError
from quant.market_data.service import BackfillTooLargeError, StaleBarsError
from quant.market_data.subscriptions import SubscriptionError
from quant.shared.db import ProcedureError
from quant.trade.errors import DeploymentNotFound, TradeValidationError

logger = logging.getLogger(__name__)


def _log(request: Request, status_code: int, detail: object) -> None:
    """Record one line for every error response these handlers produce.

    Handling an exception here consumes it, so without this the reason travels
    only in the response body and the server keeps no trace: a failure a user
    reports cannot be reconstructed afterwards, and an intermediate proxy is
    free to replace the body before they ever read it.
    """
    logger.log(
        logging.ERROR if status_code >= 500 else logging.WARNING,
        "%s %s -> %d: %s",
        request.method,
        request.url.path,
        status_code,
        detail,
    )


def _procedure_status_code(sqlstate: str) -> int:
    if sqlstate.startswith("23"):
        return status.HTTP_409_CONFLICT
    if sqlstate.startswith("22"):
        return status.HTTP_400_BAD_REQUEST
    return status.HTTP_502_BAD_GATEWAY


async def handle_procedure_error(request: Request, exc: ProcedureError) -> JSONResponse:
    status_code = _procedure_status_code(exc.sqlstate)
    _log(request, status_code, f"{exc.proc} [{exc.sqlstate}]: {exc.message}")
    return JSONResponse(
        status_code=status_code,
        content={
            "detail": {
                "proc": exc.proc,
                "sqlstate": exc.sqlstate,
                "message": exc.message,
            },
        },
    )


async def handle_database_error(request: Request, exc: psycopg.Error) -> JSONResponse:
    """The same mapping for a call that never reached the procedure's handler.

    ``handle_procedure_error`` covers a procedure that ran and reported a
    SQLSTATE in its OUT row. It cannot cover the calls that fail before that:
    the connection is gone, or the signature Python calls is not the one this
    database has. Those raise from the driver, reach Starlette unhandled, and
    become a 500 whose body is the string ``Internal Server Error`` — so the
    only thing a caller can report back is the status code, and the reason
    lives solely in a server log they cannot read.

    The driver carries the same two facts the OUT row does, so they are sent in
    the same shape and mapped by the same function rather than flattened to
    one code. ``42883`` on a write is the one worth naming: the procedure is
    absent, which means this environment is behind on a migration and no input
    the caller changes will help.
    """
    sqlstate = exc.sqlstate or ""
    message = (exc.diag.message_primary or str(exc)).strip()
    status_code = _procedure_status_code(sqlstate)
    _log(request, status_code, f"psycopg [{sqlstate}]: {message}")
    return JSONResponse(
        status_code=status_code,
        content={"detail": {"sqlstate": sqlstate, "message": message}},
    )


async def handle_bar_fetch_error(request: Request, exc: BarFetchError) -> JSONResponse:
    """502 — the exchange refused or could not be reached, which is not a 500.

    Nothing catches this on the way up, so every route that touches ccxt used
    to answer an unreachable venue with an empty-bodied 500. The distinction
    worth keeping is that a 500 invites a bug report and this invites a retry:
    the request was well formed and the venue was not there.
    """
    _log(request, status.HTTP_502_BAD_GATEWAY, exc)
    return JSONResponse(
        status_code=status.HTTP_502_BAD_GATEWAY,
        content={"detail": f"the exchange could not answer: {exc}"},
    )


async def handle_trade_validation_error(
    request: Request,
    exc: TradeValidationError,
) -> JSONResponse:
    _log(request, exc.status_code, exc)
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": str(exc)},
    )


async def handle_deployment_not_found(
    request: Request,
    exc: DeploymentNotFound,
) -> JSONResponse:
    _log(request, status.HTTP_404_NOT_FOUND, f"deployment not found: {exc}")
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": f"deployment not found: {exc}"},
    )


async def handle_stale_bars(request: Request, exc: StaleBarsError) -> JSONResponse:
    """503, not 400 — the request was fine, the exchange data was not.

    Distinguishing it matters to the scheduler: a caller seeing this should
    come back on the next tick, whereas a 4xx means retrying changes nothing.
    """
    _log(request, status.HTTP_503_SERVICE_UNAVAILABLE, exc)
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": f"price bars unavailable — no signal computed: {exc}"},
    )


async def handle_subscription_error(
    request: Request,
    exc: SubscriptionError,
) -> JSONResponse:
    """400 — the series asked for cannot be captured as described.

    An unmapped symbol or a venue this platform cannot read bars from is the
    caller's to fix, and saying so on write is the whole point of validating
    here: left to the warmer it would be a silent failure repeated every tick.
    """
    _log(request, status.HTTP_400_BAD_REQUEST, exc)
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": str(exc)},
    )


async def handle_backfill_too_large(
    request: Request,
    exc: BackfillTooLargeError,
) -> JSONResponse:
    """400 — the range is fillable in principle, just not in one blocking call.

    Refused before any work starts rather than attempted and abandoned: a fill
    that spans millions of boundaries would hold the connection past every
    proxy timeout and store nothing, so the caller would learn only that the
    request died. The message names a range that fits instead.
    """
    _log(request, status.HTTP_400_BAD_REQUEST, exc)
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": str(exc)},
    )


def register(app: FastAPI) -> None:
    app.add_exception_handler(ProcedureError, handle_procedure_error)
    app.add_exception_handler(psycopg.Error, handle_database_error)
    app.add_exception_handler(BarFetchError, handle_bar_fetch_error)
    app.add_exception_handler(TradeValidationError, handle_trade_validation_error)
    app.add_exception_handler(DeploymentNotFound, handle_deployment_not_found)
    app.add_exception_handler(StaleBarsError, handle_stale_bars)
    app.add_exception_handler(SubscriptionError, handle_subscription_error)
    app.add_exception_handler(BackfillTooLargeError, handle_backfill_too_large)
