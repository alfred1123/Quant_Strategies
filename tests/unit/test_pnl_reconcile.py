"""Strategy-bar live return: position, fill gap, and fee in quote."""

from decimal import Decimal

import pytest

from quant.trade.pnl_reconcile import StrategyFill, fee_in_quote, strategy_bar_return

_QTY = Decimal(2)
_TARGET = Decimal(2)
_CLOSE = Decimal(100)
_NEXT = Decimal(110)


def test_quote_fee_matches_the_worked_bar():
    """qty 2, target 2, closes 100 then 110, buy 2 at 101, fee 0.1 USDT."""
    bar = strategy_bar_return(
        qty=_QTY,
        target_qty=_TARGET,
        close_k=_CLOSE,
        close_k1=_NEXT,
        quote_ccy="USDT",
        base_ccy="BTC",
        fills=(
            StrategyFill(
                side="BUY",
                qty=2,
                price=101,
                fee_amt=Decimal("0.1"),
                fee_ccy="USDT",
            ),
        ),
    )
    assert bar.unit_notional_amt == Decimal(200)
    assert bar.target_position == Decimal(1)
    assert bar.position_return == Decimal("0.1")
    assert bar.fill_gap_return == Decimal("-0.01")
    assert bar.fee_return == Decimal("-0.0005")
    assert bar.live_return == Decimal("0.0895")


def test_base_fee_converts_at_the_fill_price():
    """0.001 BTC at 101 is 0.101 USDT, so the fee term is −0.101 / 200."""
    bar = strategy_bar_return(
        qty=_QTY,
        target_qty=_TARGET,
        close_k=_CLOSE,
        close_k1=_NEXT,
        quote_ccy="USDT",
        base_ccy="BTC",
        fills=(
            StrategyFill(
                side="buy",
                qty=Decimal(2),
                price=Decimal(101),
                fee_amt=Decimal("0.001"),
                fee_ccy="btc",
            ),
        ),
    )
    assert bar.fee_return == Decimal("-0.000505")
    assert bar.live_return == Decimal("0.089495")


def test_unknown_fee_currency_nulls_the_fee_and_the_live_return():
    bar = strategy_bar_return(
        qty=_QTY,
        target_qty=_TARGET,
        close_k=_CLOSE,
        close_k1=_NEXT,
        quote_ccy="USDT",
        base_ccy="BTC",
        fills=(
            StrategyFill(
                side="BUY",
                qty=2,
                price=101,
                fee_amt=Decimal("0.1"),
                fee_ccy="EUR",
            ),
        ),
    )
    assert bar.position_return == Decimal("0.1")
    assert bar.fill_gap_return == Decimal("-0.01")
    assert bar.fee_return is None
    assert bar.live_return is None


def test_missing_currency_on_a_nonzero_fee_is_unknown():
    assert (
        fee_in_quote(
            fee_amt=Decimal("0.1"),
            fee_ccy=None,
            fill_price=Decimal(101),
            quote_ccy="USDT",
            base_ccy="BTC",
        )
        is None
    )


def test_zero_or_absent_fee_is_zero():
    held = strategy_bar_return(
        qty=_QTY,
        target_qty=_TARGET,
        close_k=_CLOSE,
        close_k1=_NEXT,
        quote_ccy="USDT",
        base_ccy="BTC",
        fills=(
            StrategyFill(side="BUY", qty=2, price=101, fee_amt=0, fee_ccy=None),
            StrategyFill(side="SELL", qty=0, price=101),
        ),
    )
    # The zero-qty sell adds no gap. The buy still gaps by 2 * (100 − 101).
    assert held.fee_return == Decimal(0)
    assert held.live_return == Decimal("0.09")


def test_sell_below_the_close_is_a_negative_gap():
    bar = strategy_bar_return(
        qty=_QTY,
        target_qty=Decimal(0),
        close_k=_CLOSE,
        close_k1=_NEXT,
        quote_ccy="USDT",
        base_ccy="BTC",
        fills=(StrategyFill(side="SELL", qty=1, price=99, fee_amt=None),),
    )
    assert bar.position_return == Decimal(0)
    assert bar.fill_gap_return == Decimal("-0.005")
    assert bar.fee_return == Decimal(0)
    assert bar.live_return == Decimal("-0.005")


def test_hold_with_no_fills_is_the_position_term():
    bar = strategy_bar_return(
        qty=_QTY,
        target_qty=_TARGET,
        close_k=_CLOSE,
        close_k1=_NEXT,
        quote_ccy="USDT",
        base_ccy="BTC",
    )
    assert bar.fill_gap_return == Decimal(0)
    assert bar.fee_return == Decimal(0)
    assert bar.live_return == Decimal("0.1")


def test_zero_unit_notional_is_refused():
    with pytest.raises(ValueError, match="unit notional"):
        strategy_bar_return(
            qty=0,
            target_qty=0,
            close_k=100,
            close_k1=110,
            quote_ccy="USDT",
            base_ccy="BTC",
        )


def test_side_must_be_buy_or_sell():
    with pytest.raises(ValueError, match="BUY or SELL"):
        strategy_bar_return(
            qty=_QTY,
            target_qty=_TARGET,
            close_k=_CLOSE,
            close_k1=_NEXT,
            quote_ccy="USDT",
            base_ccy="BTC",
            fills=(StrategyFill(side="HOLD", qty=1, price=100),),
        )
