"""Trade domain errors — raised by :mod:`quant.trade.db_repo` before SP calls."""


class TradeValidationError(ValueError):
    """Invalid input or business rule violation (maps to HTTP 400/404/403 in API)."""

    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code
