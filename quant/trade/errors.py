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
    """Broker gateway unreachable or refusing to answer.

    503 rather than 502: the request was well formed and the caller should come
    back on the next tick, which is the same shape as ``StaleBarsError``.
    """

    def __init__(self, message: str, *, status_code: int = 503) -> None:
        super().__init__(message, status_code=status_code)


class BrokerAuthError(BrokerConnectionError):
    """Broker rejected the credentials.

    4xx because retrying cannot help: the key, or the environment it was issued
    for, is wrong and only the caller can fix it. Reporting it as a 5xx also
    hid the broker's own explanation, which is the actionable part — a paper
    deployment points at the venue's testnet, so mainnet keys fail here.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=400)


class OrderNotFoundError(BrokerConnectionError):
    """Broker has no record of the order yet (may still be propagating)."""


class DeploymentNotFound(Exception):
    """Requested deployment does not exist for this user (maps to HTTP 404)."""
