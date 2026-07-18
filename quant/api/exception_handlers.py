"""App-wide exception handlers — map domain/infra errors to HTTP responses."""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from quant.shared.db import ProcedureError
from quant.trade.errors import DeploymentNotFound, TradeValidationError


def _procedure_status_code(sqlstate: str) -> int:
    if sqlstate.startswith("23"):
        return status.HTTP_409_CONFLICT
    if sqlstate.startswith("22"):
        return status.HTTP_400_BAD_REQUEST
    return status.HTTP_502_BAD_GATEWAY


async def handle_procedure_error(_request: Request, exc: ProcedureError) -> JSONResponse:
    return JSONResponse(
        status_code=_procedure_status_code(exc.sqlstate),
        content={
            "detail": {
                "proc": exc.proc,
                "sqlstate": exc.sqlstate,
                "message": exc.message,
            },
        },
    )


async def handle_trade_validation_error(
    _request: Request,
    exc: TradeValidationError,
) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": str(exc)},
    )


async def handle_deployment_not_found(
    _request: Request,
    exc: DeploymentNotFound,
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": f"deployment not found: {exc}"},
    )


def register(app: FastAPI) -> None:
    app.add_exception_handler(ProcedureError, handle_procedure_error)
    app.add_exception_handler(TradeValidationError, handle_trade_validation_error)
    app.add_exception_handler(DeploymentNotFound, handle_deployment_not_found)
