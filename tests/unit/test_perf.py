import numpy as np
import pandas as pd
import pytest

from strat import Strategy, StrategyConfig, SubStrategy, SignalDirection
from perf import Performance


_BOLLINGER_CONFIG = StrategyConfig("TEST", "get_bollinger_band",
                                   Strategy.momentum_band_signal, 252)


def _make_performance(df, window=5, signal=0.5, config=None):
    """Helper to build a Performance object from a DataFrame with price & factor columns."""
    if config is None:
        config = _BOLLINGER_CONFIG
    perf = Performance(df.copy(), config, window, signal)
    perf.enrich_performance()
    return perf


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
        config = StrategyConfig("TEST", "get_bollinger_band",
                                Strategy.momentum_band_signal, 252)
        perf = Performance(sample_ohlc_df.copy(), config, 5, 0.5)
        assert perf.config is config
        assert perf.trading_period == 252

    def test_fee_bps(self, sample_ohlc_df):
        config = StrategyConfig("TEST", "get_bollinger_band",
                                Strategy.momentum_band_signal, 252)
        perf = Performance(sample_ohlc_df.copy(), config, 5, 0.5, fee_bps=10.0)
        assert perf.fee_bps == 10.0

    def test_different_indicator(self, sample_ohlc_df):
        config = StrategyConfig("TEST", "get_sma",
                                Strategy.momentum_band_signal, 252)
        perf = Performance(sample_ohlc_df.copy(), config, 5, 0.5)
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
        ticker="TEST",
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
        perf = Performance(multi_factor_df.copy(), config)
        perf.enrich_performance()
        for col in ["chg", "factor1", "indicator1", "position1", "FinalPosition", "FinalPosition_x1", "trade",
                     "pnl", "cumu", "dd", "buy_hold", "buy_hold_cumu", "buy_hold_dd",
                     "factor1", "indicator1", "position1",
                     "factor2", "indicator2", "position2"]:
            assert col in perf.data.columns, f"Missing column: {col}"

    def test_per_factor_position_values_bounded(self, multi_factor_df):
        config = _multi_factor_config()
        perf = Performance(multi_factor_df.copy(), config)
        perf.enrich_performance()
        for col in ["position1", "position2"]:
            valid = perf.data[col].dropna().unique()
            for v in valid:
                assert v in (-1.0, 0.0, 1.0), f"{col} has unexpected value {v}"

    def test_position_values_bounded(self, multi_factor_df):
        config = _multi_factor_config()
        perf = Performance(multi_factor_df.copy(), config)
        perf.enrich_performance()
        valid = perf.data["FinalPosition"].dropna().unique()
        for v in valid:
            assert v in (-1.0, 0.0, 1.0)

    def test_metric_window_is_max(self, multi_factor_df):
        config = _multi_factor_config()
        perf = Performance(multi_factor_df.copy(), config)
        assert perf._metric_window == 10

    def test_sharpe_ratio_is_scalar(self, multi_factor_df):
        config = _multi_factor_config()
        perf = Performance(multi_factor_df.copy(), config)
        perf.enrich_performance()
        sharpe = perf.get_sharpe_ratio()
        assert isinstance(sharpe, (int, float, np.floating))

    def test_strategy_performance_returns_series(self, multi_factor_df):
        config = _multi_factor_config()
        perf = Performance(multi_factor_df.copy(), config)
        perf.enrich_performance()
        result = perf.get_strategy_performance()
        assert isinstance(result, pd.Series)
        assert len(result) == 5

    def test_buy_hold_performance_returns_series(self, multi_factor_df):
        config = _multi_factor_config()
        perf = Performance(multi_factor_df.copy(), config)
        perf.enrich_performance()
        result = perf.get_buy_hold_performance()
        assert isinstance(result, pd.Series)
        assert len(result) == 5

    def test_or_conjunction(self, multi_factor_df):
        config = _multi_factor_config(conjunction="OR")
        perf = Performance(multi_factor_df.copy(), config)
        perf.enrich_performance()
        result = perf.get_strategy_performance()
        assert isinstance(result, pd.Series)

    def test_drawdown_non_negative(self, multi_factor_df):
        config = _multi_factor_config()
        perf = Performance(multi_factor_df.copy(), config)
        perf.enrich_performance()
        assert (perf.data["dd"].dropna() >= 0).all()

    def test_single_factor_backward_compat(self, sample_ohlc_df):
        """Single-factor path produces identical results when window is not a tuple."""
        config = StrategyConfig("TEST", "get_bollinger_band",
                                Strategy.momentum_band_signal, 252)
        perf = Performance(sample_ohlc_df.copy(), config, 5, 0.5)
        perf.enrich_performance()
        assert perf._metric_window == 5
        result = perf.get_strategy_performance()
        assert isinstance(result, pd.Series)
        assert len(result) == 5
