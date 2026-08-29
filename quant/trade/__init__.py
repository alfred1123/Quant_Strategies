"""Trade domain — broker-agnostic models, errors, adapters, and repos.

Broker-specific implementations live in submodules and are imported directly
(e.g. ``quant.trade.futu_trader``, ``quant.trade.brokers.ccxt``) so the package
import stays light — no broker SDKs are loaded here.
"""

from quant.trade.errors import (
    AdapterNotFoundError,
    BrokerAuthError,
    BrokerConnectionError,
    DeploymentNotFound,
    SymbolMappingError,
    TradeValidationError,
)
from quant.trade.models.order import (
    IntendedAction,
    OrderRequest,
    OrderResult,
    OrderSide,
    OrderType,
)

__all__ = [
    "AdapterNotFoundError",
    "BrokerAuthError",
    "BrokerConnectionError",
    "DeploymentNotFound",
    "IntendedAction",
    "OrderRequest",
    "OrderResult",
    "OrderSide",
    "OrderType",
    "SymbolMappingError",
    "TradeValidationError",
]
