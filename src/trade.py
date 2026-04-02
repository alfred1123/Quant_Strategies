"""Futu OpenD trade execution module.

Supports placing and managing orders for HK/US securities through the
Futu OpenD gateway.  Both paper (SIMULATE) and live (REAL) environments
are supported — controlled by the ``paper`` flag.

Usage:
    from trade import FutuTrader

    trader = FutuTrader(paper=True)          # paper trading
    trader.unlock("your_trade_password")     # unlock (required for real)
    trader.place_order("US.WEAT", 100, "BUY")
    positions = trader.get_positions()
    orders = trader.get_orders()
    trader.close()
"""

import logging
import os
import socket
from dataclasses import dataclass

import futu
from dotenv import load_dotenv

logger = logging.getLogger(__name__)


@dataclass
class OrderResult:
    """Structured result from a place_order call."""
    success: bool
    order_id: str | None
    message: str


class FutuTrader:
    """Thin wrapper around Futu OpenSecTradeContext for order management."""

    DEFAULT_TIMEOUT = 5  # seconds

    MARKET_MAP = {
        "US": futu.TrdMarket.US,
        "HK": futu.TrdMarket.HK,
        "CN": futu.TrdMarket.CN,
        "SG": futu.TrdMarket.SG,
        "JP": futu.TrdMarket.JP,
    }

    def __init__(
        self, *, paper: bool = True, timeout: int | None = None,
        market: str = "US",
    ) -> None:
        load_dotenv()
        host = os.getenv("FUTU_HOST")
        port_str = os.getenv("FUTU_PORT")
        if not host or not port_str:
            raise ValueError("FUTU_HOST and FUTU_PORT must be set in .env")

        self._host = host
        self._port = int(port_str)
        self._paper = paper
        self._trd_env = futu.TrdEnv.SIMULATE if paper else futu.TrdEnv.REAL
        self._timeout = timeout if timeout is not None else self.DEFAULT_TIMEOUT
        self._market = market.upper()

        trd_market = self.MARKET_MAP.get(self._market)
        if trd_market is None:
            raise ValueError(
                f"Unsupported market '{market}'. "
                f"Choose from: {', '.join(self.MARKET_MAP)}"
            )

        self._check_connection()

        self._ctx = futu.OpenSecTradeContext(
            host=self._host, port=self._port,
            filter_trdmarket=trd_market,
        )
        logger.info(
            "FutuTrader connected to %s:%s (market=%s, env=%s)",
            self._host, self._port, self._market,
            "SIMULATE" if paper else "REAL",
        )

    @staticmethod
    def detect_market(symbol: str) -> str:
        """Detect market from Futu symbol prefix (e.g. 'HK.00700' → 'HK')."""
        prefix = symbol.split(".")[0].upper() if "." in symbol else "US"
        return prefix

    def _check_connection(self) -> None:
        """Pre-check that Futu OpenD is reachable before creating the context."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(self._timeout)
        try:
            sock.connect((self._host, self._port))
        except (ConnectionRefusedError, socket.timeout, OSError) as exc:
            raise ConnectionError(
                f"Cannot reach Futu OpenD at {self._host}:{self._port} "
                f"(timeout={self._timeout}s). Is the gateway running?"
            ) from exc
        finally:
            sock.close()

    # ── Connection management ───────────────────────────────────────

    def close(self) -> None:
        self._ctx.close()
        logger.info("FutuTrader connection closed")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # ── Trade unlock (required for REAL env) ────────────────────────

    def unlock(self, trade_password: str) -> bool:
        ret, data = self._ctx.unlock_trade(trade_password)
        if ret != 0:
            logger.error("Trade unlock failed: %s", data)
            return False
        logger.info("Trade unlocked successfully")
        return True

    # ── Order placement ─────────────────────────────────────────────

    def place_order(
        self,
        symbol: str,
        qty: int,
        side: str,
        *,
        order_type: str = "MARKET",
        price: float | None = None,
    ) -> OrderResult:
        """Place a buy or sell order.

        Args:
            symbol: Futu symbol (e.g. 'US.WEAT').
            qty: Number of shares.
            side: 'BUY' or 'SELL'.
            order_type: 'MARKET' or 'NORMAL' (limit). Defaults to MARKET.
            price: Limit price (required for NORMAL orders).

        Returns:
            OrderResult with success status, order_id, and message.
        """
        futu_side = futu.TrdSide.BUY if side.upper() == "BUY" else futu.TrdSide.SELL

        if order_type.upper() == "MARKET":
            futu_order_type = futu.OrderType.MARKET
        else:
            futu_order_type = futu.OrderType.NORMAL

        if futu_order_type == futu.OrderType.NORMAL and price is None:
            return OrderResult(False, None, "Limit price required for NORMAL orders")

        logger.info(
            "Placing order: %s %s %d @ %s (env=%s)",
            side, symbol, qty, order_type,
            "SIMULATE" if self._paper else "REAL",
        )

        ret, data = self._ctx.place_order(
            price=price or 0.0,
            qty=qty,
            code=symbol,
            trd_side=futu_side,
            order_type=futu_order_type,
            trd_env=self._trd_env,
        )

        if ret != 0:
            msg = str(data)
            logger.error("Order failed: %s", msg)
            return OrderResult(False, None, msg)

        order_id = str(data["order_id"].iloc[0])
        logger.info("Order placed: id=%s", order_id)
        return OrderResult(True, order_id, "Order placed successfully")

    # ── Order management ────────────────────────────────────────────

    def cancel_order(self, order_id: str) -> bool:
        ret, data = self._ctx.modify_order(
            futu.ModifyOrderOp.CANCEL, order_id, 0, 0,
            trd_env=self._trd_env,
        )
        if ret != 0:
            logger.error("Cancel failed for order %s: %s", order_id, data)
            return False
        logger.info("Order %s cancelled", order_id)
        return True

    def cancel_all_orders(self) -> bool:
        ret, data = self._ctx.cancel_all_order(trd_env=self._trd_env)
        if ret != 0:
            logger.error("Cancel all failed: %s", data)
            return False
        logger.info("All orders cancelled")
        return True

    # ── Queries ─────────────────────────────────────────────────────

    def get_positions(self):
        """Return current positions as a DataFrame."""
        ret, data = self._ctx.position_list_query(trd_env=self._trd_env)
        if ret != 0:
            logger.error("Position query failed: %s", data)
            return None
        return data

    def get_orders(self):
        """Return today's order list as a DataFrame."""
        ret, data = self._ctx.order_list_query(trd_env=self._trd_env)
        if ret != 0:
            logger.error("Order list query failed: %s", data)
            return None
        return data

    def get_account_info(self):
        """Return account balance/info as a DataFrame."""
        ret, data = self._ctx.accinfo_query(trd_env=self._trd_env)
        if ret != 0:
            logger.error("Account info query failed: %s", data)
            return None
        return data

    # ── Signal-based trading ────────────────────────────────────────

    def apply_signal(
        self,
        symbol: str,
        signal_value: float,
        qty: int,
    ) -> OrderResult | None:
        """Translate a strategy signal into an order.

        Args:
            symbol: Futu symbol (e.g. 'US.WEAT').
            signal_value: Strategy output: 1 = long, -1 = short, 0 = flat.
            qty: Share quantity per trade.

        Returns:
            OrderResult if an order was placed, None if no action needed.
        """
        positions = self.get_positions()
        current_qty = 0
        if positions is not None and not positions.empty:
            pos_row = positions[positions["code"] == symbol]
            if not pos_row.empty:
                current_qty = int(pos_row.iloc[0]["qty"])

        if signal_value == 1 and current_qty <= 0:
            if current_qty < 0:
                # Close short first
                self.place_order(symbol, abs(current_qty), "BUY")
            return self.place_order(symbol, qty, "BUY")

        if signal_value == -1 and current_qty >= 0:
            if current_qty > 0:
                # Close long first
                self.place_order(symbol, current_qty, "SELL")
            return self.place_order(symbol, qty, "SELL")

        if signal_value == 0 and current_qty != 0:
            side = "SELL" if current_qty > 0 else "BUY"
            return self.place_order(symbol, abs(current_qty), side)

        logger.info("No action needed for signal=%.0f, current_qty=%d", signal_value, current_qty)
        return None
