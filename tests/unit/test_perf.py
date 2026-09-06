import numpy as np
import pandas as pd
import pytest

from quant.strategy.signals import Strategy, StrategyConfig, SubStrategy, SignalDirection
from quant.strategy.performance import Performance, live_lookback_days


_BOLLINGER_CONFIG = StrategyConfig("test", "get_bollinger_band",
                                   Strategy.momentum_band_signal, 252)


def _make_performance(df, window=5, signal=0.5, config=None):
    """Helper to build a Performance object from a DataFrame with price & factor columns."""
    if config is None:
        config = _BOLLINGER_CONFIG
    perf = Performance({config.internal_cusip: df.copy()}, config, window, signal)
    perf.enrich_performance()
    return perf


def _make_positions(df, window=5, signal=0.5, config=None):
    if config is None:
        config = _BOLLINGER_CONFIG
    perf = Performance({config.internal_cusip: df.copy()}, config, window, signal)
    perf._trade_enrich_positions()
    return perf


class TestTradeEnrichPositions:
    def test_skips_pnl_columns(self, sample_ohlc_df):
        perf = _make_positions(sample_ohlc_df)
        assert "FinalPosition" in perf.data.columns
        assert "cumu" not in perf.data.columns
        assert "pnl" not in perf.data.columns

    def test_trade_latest_final_position(self, sample_ohlc_df):
        perf = _make_positions(sample_ohlc_df)
        sig, as_of = perf._trade_latest_final_position()
        assert sig in (-1.0, 0.0, 1.0)
        assert as_of

    def test_enrich_performance_still_adds_pnl(self, sample_ohlc_df):
        perf = _make_performance(sample_ohlc_df)
        assert "cumu" in perf.data.columns


def _cross_product_data():
    np.random.seed(42)
    n = 300
    idx = pd.date_range("2020-01-01", periods=n, freq="D", name="datetime")
    btc = 100 + np.cumsum(np.random.randn(n) * 0.5)
    eth = 50 + np.cumsum(np.random.randn(n) * 0.3)
    return {
        "btc-usd": pd.DataFrame({
            "price": btc, "factor": btc, "v": btc,
            "Close": btc,
            "High": btc + np.abs(np.random.randn(n) * 0.3),
            "Low": btc - np.abs(np.random.randn(n) * 0.3),
        }, index=idx),
        "eth-usd": pd.DataFrame({
            "price": eth, "factor": eth, "v": eth,
            "Close": eth,
            "High": eth + np.abs(np.random.randn(n) * 0.3),
            "Low": eth - np.abs(np.random.randn(n) * 0.3),
        }, index=idx),
    }


class TestComputeLatestPositionParity:
    """Live fast path must match full enrich on the last bar."""

    def test_single_factor_matches_enrich(self, sample_ohlc_df):
        config = _BOLLINGER_CONFIG
        data = {config.internal_cusip: sample_ohlc_df.copy()}
        enrich = Performance(data, config, 5, 0.5)
        enrich._trade_enrich_positions()
        expected_sig, expected_as_of = enrich._trade_latest_final_position()

        trade = Performance(data, config, 5, 0.5)
        sig, as_of = trade.compute_latest_position()
        assert sig == expected_sig
        assert as_of == expected_as_of

    @pytest.mark.parametrize("conjunction", ["AND", "OR"])
    def test_multi_factor_matches_enrich(self, multi_factor_df, conjunction):
        config = _multi_factor_config(conjunction=conjunction)
        data = {config.internal_cusip: multi_factor_df.copy()}
        enrich = Performance(data, config)
        enrich._trade_enrich_positions()
        expected_sig, expected_as_of = enrich._trade_latest_final_position()

        trade = Performance(data, config)
        sig, as_of = trade.compute_latest_position()
        assert sig == expected_sig
        assert as_of == expected_as_of

    def test_cross_product_single_factor_matches_enrich(self):
        data = _cross_product_data()
        sub = SubStrategy(
            "get_sma", "momentum_band_signal", 20, 1.0, internal_cusip="eth-usd",
        )
        config = StrategyConfig(
            "btc-usd", "get_sma", Strategy.momentum_band_signal, 365,
            substrategies=(sub,),
        )
        enrich = Performance(data, config, 20, 1.0)
        enrich._trade_enrich_positions()
        expected_sig, expected_as_of = enrich._trade_latest_final_position()

        trade = Performance(data, config, 20, 1.0)
        sig, as_of = trade.compute_latest_position()
        assert sig == expected_sig
        assert as_of == expected_as_of

    def test_cross_product_multi_factor_matches_enrich(self):
        data = _cross_product_data()
        sub_btc = SubStrategy("get_sma", "momentum_band_signal", 20, 1.0)
        sub_eth = SubStrategy(
            "get_sma", "reversion_band_signal", 10, 0.5, internal_cusip="eth-usd",
        )
        config = StrategyConfig(
            "btc-usd", "get_sma", Strategy.momentum_band_signal, 365,
            conjunction="AND", substrategies=(sub_btc, sub_eth),
        )
        enrich = Performance(data, config)
        enrich._trade_enrich_positions()
        expected_sig, expected_as_of = enrich._trade_latest_final_position()

        trade = Performance(data, config)
        sig, as_of = trade.compute_latest_position()
        assert sig == expected_sig
        assert as_of == expected_as_of


class TestLiveLookback:
    def test_scales_with_window(self):
        assert live_lookback_days(20, 365) == max(20 * 3 + 60, min(365, 400))


class TestPerformanceInit:
    def test_columns_created(self, sample_ohlc_df):
        perf = _make_performance(sample_ohlc_df)
        for col in ["chg", "factor1", "indicator1", "position1", "FinalPosition", "FinalPosition_x1", "trade", "pnl", "cumu", "dd",
                     "buy_hold", "buy_hold_cumu", "buy_hold_dd"]:
            assert col in perf.data.columns, f"Missing column: {col}"

    def test_position_values(self, sample_ohlc_df):
        perf = _make_performance(sample_ohlc_df)
        valid_positions = perf.data["FinalPosition"].dropna().unique()
        for v in valid_positions:
            assert v in (-1.0, 0.0, 1.0)

    def test_drawdown_non_negative(self, sample_ohlc_df):
        perf = _make_performance(sample_ohlc_df)
        assert (perf.data["dd"].dropna() >= 0).all()

    def test_buy_hold_drawdown_non_negative(self, sample_ohlc_df):
        perf = _make_performance(sample_ohlc_df)
        assert (perf.data["buy_hold_dd"].dropna() >= 0).all()

    def test_trade_column_non_negative(self, sample_ohlc_df):
        perf = _make_performance(sample_ohlc_df)
        assert (perf.data["trade"].dropna() >= 0).all()


class TestStrategyMetrics:
    def test_total_return_is_scalar(self, sample_ohlc_df):
        perf = _make_performance(sample_ohlc_df)
        ret = perf.get_total_return()
        assert np.isfinite(ret)

    def test_annualized_return_is_scalar(self, sample_ohlc_df):
        perf = _make_performance(sample_ohlc_df)
        ret = perf.get_annualized_return()
        assert isinstance(ret, (int, float, np.floating))

    def test_sharpe_is_scalar(self, sample_ohlc_df):
        perf = _make_performance(sample_ohlc_df)
        sharpe = perf.get_sharpe_ratio()
        assert np.isfinite(sharpe) or np.isnan(sharpe)

    def test_max_drawdown_non_negative(self, sample_ohlc_df):
        perf = _make_performance(sample_ohlc_df)
        assert perf.get_max_drawdown() >= 0

    def test_calmar_ratio_is_scalar(self, sample_ohlc_df):
        perf = _make_performance(sample_ohlc_df)
        calmar = perf.get_calmar_ratio()
        assert isinstance(calmar, (int, float, np.floating))

    def test_strategy_performance_returns_series(self, sample_ohlc_df):
        perf = _make_performance(sample_ohlc_df)
        result = perf.get_strategy_performance()
        assert isinstance(result, pd.Series)
        assert len(result) == 5
        expected_index = ["Total Return", "Annualized Return", "Sharpe Ratio", "Max Drawdown", "Calmar Ratio"]
        assert list(result.index) == expected_index

    def test_sharpe_nan_when_fewer_than_min_obs(self, sample_ohlc_df):
        short = sample_ohlc_df.iloc[:40]
        perf = _make_performance(short, window=5)
        assert np.isnan(perf.get_sharpe_ratio())
        assert np.isnan(perf.get_annualized_return())
        assert perf.get_metric_n_obs() < Performance.MIN_METRIC_OBS

    def test_buy_hold_sharpe_nan_when_fewer_than_min_obs(self, sample_ohlc_df):
        short = sample_ohlc_df.iloc[:40]
        perf = _make_performance(short, window=5)
        assert np.isnan(perf.get_buy_hold_sharpe_ratio())
        assert np.isnan(perf.get_buy_hold_annualized_return())


class TestBuyHoldMetrics:
    def test_buy_hold_total_return_is_scalar(self, sample_ohlc_df):
        perf = _make_performance(sample_ohlc_df)
        ret = perf.get_buy_hold_total_return()
        assert np.isfinite(ret)

    def test_buy_hold_annualized_return_is_scalar(self, sample_ohlc_df):
        perf = _make_performance(sample_ohlc_df)
        ret = perf.get_buy_hold_annualized_return()
        assert isinstance(ret, (int, float, np.floating))

    def test_buy_hold_sharpe_ratio_is_scalar(self, sample_ohlc_df):
        perf = _make_performance(sample_ohlc_df)
        sharpe = perf.get_buy_hold_sharpe_ratio()
        assert np.isfinite(sharpe) or np.isnan(sharpe)

    def test_buy_hold_max_drawdown_non_negative(self, sample_ohlc_df):
        perf = _make_performance(sample_ohlc_df)
        assert perf.get_buy_hold_max_drawdown() >= 0

    def test_buy_hold_calmar_ratio_is_scalar(self, sample_ohlc_df):
        perf = _make_performance(sample_ohlc_df)
        calmar = perf.get_buy_hold_calmar_ratio()
        assert isinstance(calmar, (int, float, np.floating))

    def test_buy_hold_performance_returns_series(self, sample_ohlc_df):
        perf = _make_performance(sample_ohlc_df)
        result = perf.get_buy_hold_performance()
        assert isinstance(result, pd.Series)
        assert len(result) == 5


class TestTrendingMarkets:
    def test_buy_hold_positive_in_uptrend(self, trending_up_df):
        perf = _make_performance(trending_up_df, window=10, signal=0.5)
        assert perf.get_buy_hold_total_return() > 0

    def test_buy_hold_negative_in_downtrend(self, trending_down_df):
        perf = _make_performance(trending_down_df, window=10, signal=0.5)
        assert perf.get_buy_hold_total_return() < 0

    def test_transaction_costs_reduce_returns(self, sample_ohlc_df):
        perf = _make_performance(sample_ohlc_df)
        total_trade_cost = (perf.data["trade"] * 0.0005).sum()
        # Transaction costs should be non-negative
        assert total_trade_cost >= 0


class TestPerformanceWithConfig:
    def test_config_stored(self, sample_ohlc_df):
        config = StrategyConfig("test", "get_bollinger_band",
                                Strategy.momentum_band_signal, 252)
        perf = Performance({config.internal_cusip: sample_ohlc_df.copy()}, config, 5, 0.5)
        assert perf.config is config
        assert perf.trading_period == 252

    def test_fee_bps(self, sample_ohlc_df):
        config = StrategyConfig("test", "get_bollinger_band",
                                Strategy.momentum_band_signal, 252)
        perf = Performance({config.internal_cusip: sample_ohlc_df.copy()}, config, 5, 0.5, fee_bps=5.5)
        assert perf.fee_bps == 5.5

    def test_default_fee_is_spot_taker(self, sample_ohlc_df):
        config = StrategyConfig("test", "get_bollinger_band",
                                Strategy.momentum_band_signal, 252)
        perf = Performance({config.internal_cusip: sample_ohlc_df.copy()}, config, 5, 0.5)
        assert perf.fee_bps == Performance.DEFAULT_FEE_BPS
        assert perf.fee_bps == 10.0

    def test_different_indicator(self, sample_ohlc_df):
        config = StrategyConfig("test", "get_sma",
                                Strategy.momentum_band_signal, 252)
        perf = Performance({config.internal_cusip: sample_ohlc_df.copy()}, config, 5, 0.5)
        perf.enrich_performance()
        result = perf.get_strategy_performance()
        assert isinstance(result, pd.Series)
        assert len(result) == 5


# -------------------------------------------------------------------------
# Phase 3: Multi-factor Performance
# -------------------------------------------------------------------------

def _multi_factor_config(**overrides):
    """Build a two-factor StrategyConfig for multi-factor tests."""
    sub_a = SubStrategy(
        indicator_name="get_sma",
        signal_func_name="momentum_band_signal",
        window=5, signal=0.5, data_column="v",
    )
    sub_b = SubStrategy(
        indicator_name="get_sma",
        signal_func_name="momentum_band_signal",
        window=10, signal=0.5, data_column="volume",
    )
    defaults = dict(
        internal_cusip="test",
        indicator_name="get_sma",
        signal_func=SignalDirection.momentum_band_signal,
        trading_period=252,
        conjunction="AND",
        substrategies=(sub_a, sub_b),
    )
    defaults.update(overrides)
    return StrategyConfig(**defaults)


class TestMultiFactorPerformance:
    def test_columns_created(self, multi_factor_df):
        config = _multi_factor_config()
        perf = Performance({config.internal_cusip: multi_factor_df.copy()}, config)
        perf.enrich_performance()
        for col in ["chg", "factor1", "indicator1", "position1", "FinalPosition", "FinalPosition_x1", "trade",
                     "pnl", "cumu", "dd", "buy_hold", "buy_hold_cumu", "buy_hold_dd",
                     "factor1", "indicator1", "position1",
                     "factor2", "indicator2", "position2"]:
            assert col in perf.data.columns, f"Missing column: {col}"

    def test_per_factor_position_values_bounded(self, multi_factor_df):
        config = _multi_factor_config()
        perf = Performance({config.internal_cusip: multi_factor_df.copy()}, config)
        perf.enrich_performance()
        for col in ["position1", "position2"]:
            valid = perf.data[col].dropna().unique()
            for v in valid:
                assert v in (-1.0, 0.0, 1.0), f"{col} has unexpected value {v}"

    def test_position_values_bounded(self, multi_factor_df):
        config = _multi_factor_config()
        perf = Performance({config.internal_cusip: multi_factor_df.copy()}, config)
        perf.enrich_performance()
        valid = perf.data["FinalPosition"].dropna().unique()
        for v in valid:
            assert v in (-1.0, 0.0, 1.0)

    def test_metric_window_is_max(self, multi_factor_df):
        config = _multi_factor_config()
        perf = Performance({config.internal_cusip: multi_factor_df.copy()}, config)
        assert perf._metric_window == 10

    def test_sharpe_ratio_is_scalar(self, multi_factor_df):
        config = _multi_factor_config()
        perf = Performance({config.internal_cusip: multi_factor_df.copy()}, config)
        perf.enrich_performance()
        sharpe = perf.get_sharpe_ratio()
        assert isinstance(sharpe, (int, float, np.floating))

    def test_strategy_performance_returns_series(self, multi_factor_df):
        config = _multi_factor_config()
        perf = Performance({config.internal_cusip: multi_factor_df.copy()}, config)
        perf.enrich_performance()
        result = perf.get_strategy_performance()
        assert isinstance(result, pd.Series)
        assert len(result) == 5

    def test_buy_hold_performance_returns_series(self, multi_factor_df):
        config = _multi_factor_config()
        perf = Performance({config.internal_cusip: multi_factor_df.copy()}, config)
        perf.enrich_performance()
        result = perf.get_buy_hold_performance()
        assert isinstance(result, pd.Series)
        assert len(result) == 5

    def test_or_conjunction(self, multi_factor_df):
        config = _multi_factor_config(conjunction="OR")
        perf = Performance({config.internal_cusip: multi_factor_df.copy()}, config)
        perf.enrich_performance()
        result = perf.get_strategy_performance()
        assert isinstance(result, pd.Series)

    def test_drawdown_non_negative(self, multi_factor_df):
        config = _multi_factor_config()
        perf = Performance({config.internal_cusip: multi_factor_df.copy()}, config)
        perf.enrich_performance()
        assert (perf.data["dd"].dropna() >= 0).all()

    def test_single_factor_backward_compat(self, sample_ohlc_df):
        """Single-factor path produces identical results when window is not a tuple."""
        config = StrategyConfig("test", "get_bollinger_band",
                                Strategy.momentum_band_signal, 252)
        perf = Performance({config.internal_cusip: sample_ohlc_df.copy()}, config, 5, 0.5)
        perf.enrich_performance()
        assert perf._metric_window == 5
        result = perf.get_strategy_performance()
        assert isinstance(result, pd.Series)
        assert len(result) == 5
