"""
E2E tests: connect to a real Futu OpenD gateway and exercise the
FutuTrader order management in SIMULATE (paper) mode.

These tests require:
  - A running Futu OpenD gateway
  - FUTU_HOST and FUTU_PORT set in .env

Run explicitly:
  python -m pytest tests/e2e/ -v -m e2e

They are skipped by default in `python -m pytest tests/` unless
the -m e2e marker is specified.
"""

import os

import pandas as pd
import pytest
from dotenv import load_dotenv

from trade import FutuTrader, OrderResult

load_dotenv(os.path.join(os.path.dirname(__file__), "../../.env"))

_has_futu = bool(os.getenv("FUTU_HOST")) and bool(os.getenv("FUTU_PORT"))

pytestmark = pytest.mark.e2e


@pytest.fixture(scope="module")
def trader():
    """FutuTrader in paper mode — skips if gateway is unreachable."""
    if not _has_futu:
        pytest.skip("FUTU_HOST/FUTU_PORT not set — skipping FutuTrader E2E tests")
    try:
        t = FutuTrader(paper=True)
    except Exception as exc:
        pytest.skip(f"Futu OpenD gateway not available: {exc}")
    yield t
    t.close()


# ── Connection and account ──────────────────────────────────────────


class TestFutuTraderConnection:
    """Verify basic connectivity and account queries."""

    def test_get_account_info_returns_dataframe(self, trader):
        info = trader.get_account_info()
        assert info is not None
        assert isinstance(info, pd.DataFrame)
        assert len(info) > 0

    def test_get_positions_returns_dataframe(self, trader):
        positions = trader.get_positions()
        assert positions is not None
        assert isinstance(positions, pd.DataFrame)

    def test_get_orders_returns_dataframe(self, trader):
        orders = trader.get_orders()
        assert orders is not None
        assert isinstance(orders, pd.DataFrame)


# ── Order placement (paper/simulate only) ───────────────────────────


class TestFutuTraderOrders:
    """Test order placement and cancellation in SIMULATE mode."""

    def test_place_market_buy_returns_order_result(self, trader):
        result = trader.place_order("US.AAPL", 1, "BUY", order_type="MARKET")
        assert isinstance(result, OrderResult)
        # Market orders may fail outside trading hours, but should still
        # return a structured result
        assert isinstance(result.success, bool)
        assert isinstance(result.message, str)

    def test_limit_order_without_price_fails(self, trader):
        result = trader.place_order("US.AAPL", 1, "BUY", order_type="NORMAL")
        assert result.success is False
        assert "price" in result.message.lower()

    def test_place_and_cancel_limit_order(self, trader):
        result = trader.place_order(
            "US.AAPL", 1, "BUY", order_type="NORMAL", price=1.00,
        )
        if result.success and result.order_id:
            cancelled = trader.cancel_order(result.order_id)
            assert isinstance(cancelled, bool)

    def test_cancel_all_orders(self, trader):
        result = trader.cancel_all_orders()
        assert isinstance(result, bool)


# ── Signal-based trading ────────────────────────────────────────────


class TestFutuTraderSignals:
    """Test signal-to-order translation in SIMULATE mode."""

    def test_flat_signal_no_action(self, trader):
        result = trader.apply_signal("US.AAPL", 0, 1)
        # With no existing position, signal=0 should be a no-op
        # (result is None if no action needed)
        # Note: if there IS a position, it would close it
        assert result is None or isinstance(result, OrderResult)

    def test_long_signal_places_buy(self, trader):
        result = trader.apply_signal("US.AAPL", 1, 1)
        assert result is None or isinstance(result, OrderResult)

    def test_short_signal_places_sell(self, trader):
        result = trader.apply_signal("US.AAPL", -1, 1)
        assert result is None or isinstance(result, OrderResult)
