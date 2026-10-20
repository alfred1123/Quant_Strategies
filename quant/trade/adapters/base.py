"""Abstract broker session and trade adapter interfaces.

An adapter places, cancels and reads. It does not decide: what order a
signal and a position call for is :mod:`quant.trade.order_policy`, so every
broker executes the same reading of the same signal.
"""

from abc import ABC, abstractmethod

from quant.trade.models.key_profile import KeyProfile
from quant.trade.models.order import OrderRequest, OrderResult
from quant.trade.models.session import BrokerSessionState


class BrokerSession(ABC):
    """Lifecycle: connect → (optional unlock) → use → disconnect."""

    @abstractmethod
    def connect(self) -> None: ...

    @abstractmethod
    def disconnect(self) -> None: ...

    @abstractmethod
    def health(self) -> BrokerSessionState: ...

    def __enter__(self) -> "BrokerSession":
        self.connect()
        return self

    def __exit__(self, *exc) -> None:
        self.disconnect()


class TradeAdapter(BrokerSession):
    """Broker-agnostic trading surface for the execution loop."""

    @abstractmethod
    def unlock_live_trading(self, trade_password: str) -> None:
        """Required for REAL env; no-op or skip for paper."""

    @abstractmethod
    def place_order(self, req: OrderRequest) -> OrderResult: ...

    @abstractmethod
    def cancel_order(
        self, vendor_order_id: str, vendor_symbol: str | None = None
    ) -> OrderResult:
        """Cancel one order. Most ccxt exchanges require the symbol too."""

    @abstractmethod
    def get_open_orders(self, symbol: str | None = None) -> list[dict]: ...

    @abstractmethod
    def get_position_qty(self, symbol: str) -> float: ...

    def get_last_price(self, symbol: str) -> float | None:
        """Best-effort last traded price for notional estimates; ``None`` if unavailable."""
        return None

    @property
    def key_profile(self) -> KeyProfile | None:
        """What the venue said about this session's API key, once connected.

        ``None`` for brokers that do not route or introspect keys (Futu), and
        before :meth:`connect`. Concrete rather than abstract for the same
        reason as :meth:`get_balances`.
        """
        return None

    def get_balances(self) -> list[dict]:
        """Per-currency cash — ``code``, ``free``, ``used``, ``total``.

        Concrete rather than abstract: a broker with no balance endpoint
        reports nothing instead of forcing every adapter to implement a stub,
        and the caller renders an empty table either way.
        """
        return []

    def get_open_positions(self) -> list[dict]:
        """Every open position on the account, not just deployed symbols.

        Distinct from :meth:`get_position_qty`, which answers "what is my
        exposure to *this* symbol" for a trade decision. This answers "what does
        this account hold", so it surfaces manual trades and positions left by a
        stopped deployment.
        """
        return []

    @abstractmethod
    def validate_for_dry_run(self, internal_cusip: str, app_id: int) -> str:
        """Validate credentials + symbol mapping. Returns vendor symbol."""
