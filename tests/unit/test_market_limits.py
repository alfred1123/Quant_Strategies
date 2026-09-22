"""Unit tests for :class:`quant.trade.models.market.MarketLimits`."""

from quant.trade.models.market import MarketLimits


class TestMinQty:
    def test_a_qty_under_the_lot_size_is_refused(self):
        limits = MarketLimits("BTCUSDT", min_qty=0.001)
        message = limits.undersized(0.0001)
        assert message is not None
        assert "0.0001" in message
        assert "BTCUSDT min qty 0.001" in message

    def test_the_lot_size_itself_is_accepted(self):
        assert MarketLimits("BTCUSDT", min_qty=0.001).undersized(0.001) is None

    def test_an_unpublished_lot_size_enforces_nothing(self):
        assert MarketLimits("BTCUSDT").undersized(0.000001) is None


class TestMinNotional:
    def test_a_qty_worth_less_than_the_floor_is_refused(self):
        limits = MarketLimits("BNBUSDT", min_notional=5.0)
        message = limits.undersized(0.001, price=350.0)
        assert message is not None
        assert "min notional 5" in message

    def test_a_qty_worth_more_than_the_floor_passes(self):
        limits = MarketLimits("BNBUSDT", min_notional=5.0)
        assert limits.undersized(0.1, price=350.0) is None

    def test_without_a_quote_the_notional_rule_is_skipped(self):
        """No price means no opinion — the venue's own reject is what we record."""
        limits = MarketLimits("BNBUSDT", min_notional=5.0)
        assert limits.undersized(0.001, price=None) is None

    def test_the_lot_size_is_reported_before_the_notional(self):
        limits = MarketLimits("BTCUSDT", min_qty=0.001, min_notional=5.0)
        message = limits.undersized(0.0001, price=64000.0)
        assert message is not None and "min qty" in message


class TestNoOrder:
    def test_zero_qty_is_not_judged(self):
        """``execute_action`` already declines a zero-qty order."""
        assert MarketLimits("BTCUSDT", min_qty=0.001).undersized(0.0) is None
