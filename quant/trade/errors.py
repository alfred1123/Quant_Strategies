"""Trade domain errors — raised by :mod:`quant.trade.db_repo` before SP calls."""


class TradeValidationError(ValueError):
    """Invalid input or business rule violation (maps to HTTP 400/404/403 in API)."""

    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


class SymbolMappingError(TradeValidationError):
    """``(internal_cusip, app_id)`` cannot be resolved via INST.PRODUCT_XREF."""

    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=400)


class AdapterNotFoundError(TradeValidationError):
    """No broker adapter registered for the requested ``app_id``."""

    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=400)


class BrokerConnectionError(TradeValidationError):
    """Broker gateway unreachable or credentials rejected."""

    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=502)


class DeploymentNotFound(Exception):
    """Requested deployment does not exist for this user (maps to HTTP 404)."""
