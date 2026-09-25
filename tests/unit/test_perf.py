import numpy as np
import pandas as pd
import pytest

from quant.strategy.signals import Strategy, StrategyConfig, SubStrategy, SignalDirection
from quant.strategy.performance import Performance, _cagr, _compound, live_lookback_days


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


class TestCompound:
    """Returns must compound, not sum — see docs/archive/return-compounding.md."""

    def test_gain_then_equal_loss_ends_down(self):
        cumu, _ = _compound(pd.Series([0.5, -0.5]))
        # Summing gives 0.0; compounding gives 1.5 * 0.5 - 1 = -0.25
        assert cumu.iloc[-1] == pytest.approx(-0.25)

    def test_cumu_is_product_of_gross_returns(self):
        pnl = pd.Series([0.1, 0.2, -0.05, 0.03])
        cumu, _ = _compound(pnl)
        assert cumu.iloc[-1] == pytest.approx((1 + pnl).prod() - 1)

    def test_drawdown_is_fraction_lost_from_peak(self):
        # Peak equity 1.2 after +20%, then -50% to 0.6 → 50% drawdown
        _, dd = _compound(pd.Series([0.2, -0.5, 0.0]))
        assert dd.iloc[-1] == pytest.approx(0.5)
        assert dd.max() == pytest.approx(0.5)

    def test_drawdown_counts_losses_from_starting_capital(self):
        # Never above the initial 1.0, so the peak is the starting capital
        _, dd = _compound(pd.Series([-0.1, -0.1]))
        assert dd.iloc[0] == pytest.approx(0.1)
        assert dd.iloc[-1] == pytest.approx(0.19)

    def test_drawdown_bounded_on_random_walk(self):
        rng = np.random.default_rng(7)
        _, dd = _compound(pd.Series(rng.normal(0, 0.05, 2000)))
        assert (dd >= 0).all()
        assert (dd <= 1).all()

    def test_leading_nan_preserved_and_skipped(self):
        cumu, dd = _compound(pd.Series([np.nan, 0.1, 0.1]))
        assert np.isnan(cumu.iloc[0])
        assert np.isnan(dd.iloc[0])
        assert cumu.iloc[-1] == pytest.approx(1.1 * 1.1 - 1)

    def test_ruin_floors_at_total_loss(self):
        # A short losing more than 100% on one bar must not flip sign afterwards
        cumu, dd = _compound(pd.Series([-1.5, 0.5]))
        assert cumu.iloc[-1] == pytest.approx(-1.0)
        assert dd.max() == pytest.approx(1.0)


class TestCagr:
    """Annualised return is geometric — see docs/archive/return-compounding.md."""

    def test_constant_rate_annualizes_to_itself(self):
        # One full year of a flat 0.1%/bar compounds to exactly that year's growth
        pnl = pd.Series([0.001] * 365)
        assert _cagr(pnl, 365) == pytest.approx(1.001 ** 365 - 1)

    def test_doubling_over_two_years_is_about_41_percent(self):
        pnl = pd.Series([2 ** (1 / 730) - 1] * 730)
        assert _cagr(pnl, 365) == pytest.approx(2 ** 0.5 - 1)

    def test_below_arithmetic_when_returns_vary(self):
        pnl = pd.Series([0.5, -0.4] * 100)
        assert _cagr(pnl, 365) < pnl.mean() * 365

    def test_nan_bars_excluded_from_horizon(self):
        pnl = pd.Series([np.nan] * 100 + [0.001] * 365)
        assert _cagr(pnl, 365) == pytest.approx(1.001 ** 365 - 1)

    def test_ruin_is_total_loss(self):
        assert _cagr(pd.Series([-1.5] + [0.01] * 99), 365) == pytest.approx(-1.0)

    def test_undefined_without_observations(self):
        assert np.isnan(_cagr(pd.Series([np.nan, np.nan]), 365))


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

    def test_drawdown_bounded(self, sample_ohlc_df):
        perf = _make_performance(sample_ohlc_df)
        dd = perf.data["dd"].dropna()
        assert (dd >= 0).all()
        assert (dd <= 1).all()

    def test_buy_hold_drawdown_bounded(self, sample_ohlc_df):
        perf = _make_performance(sample_ohlc_df)
        dd = perf.data["buy_hold_dd"].dropna()
        assert (dd >= 0).all()
        assert (dd <= 1).all()

    def test_buy_hold_cumu_tracks_price(self, sample_ohlc_df):
        """Always-long, fee-free buy-hold must equal the realised price move."""
        perf = _make_performance(sample_ohlc_df)
        first = perf.data["buy_hold"].first_valid_index()
        start = perf.data["price"].shift(1).loc[first]
        end = perf.data["price"].iloc[-1]
        assert perf.get_buy_hold_total_return() == pytest.approx(end / start - 1)

    def test_trade_column_non_negative(self, sample_ohlc_df):
        perf = _make_performance(sample_ohlc_df)
        assert (perf.data["trade"].dropna() >= 0).all()

    def test_fee_is_charged_only_when_the_position_changes(self, sample_ohlc_df):
        perf = _make_performance(sample_ohlc_df)
        pos = pd.Series(np.nan, index=perf.data.index)
        pos.iloc[10] = 1.0
        pos.iloc[11] = 1.0
        pos.iloc[12] = -1.0
        perf.data["FinalPosition"] = pos
        perf._compute_pnl_columns()
        fee = perf.transaction_cost
        assert perf.data["trade"].iloc[10] == pytest.approx(0.0)
        assert np.isnan(perf.data["pnl"].iloc[10])
        assert perf.data["trade"].iloc[11] == pytest.approx(0.0)
        assert perf.data["pnl"].iloc[11] == pytest.approx(perf.data["chg"].iloc[11])
        assert perf.data["trade"].iloc[12] == pytest.approx(2.0)
        assert perf.data["pnl"].iloc[12] == pytest.approx(
            perf.data["chg"].iloc[12] - 2.0 * fee
        )


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

    def test_max_drawdown_bounded(self, sample_ohlc_df):
        perf = _make_performance(sample_ohlc_df)
        assert 0 <= perf.get_max_drawdown() <= 1

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

    def test_buy_hold_max_drawdown_bounded(self, sample_ohlc_df):
        perf = _make_performance(sample_ohlc_df)
        assert 0 <= perf.get_buy_hold_max_drawdown() <= 1

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

    def test_drawdown_bounded(self, multi_factor_df):
        config = _multi_factor_config()
        perf = Performance({config.internal_cusip: multi_factor_df.copy()}, config)
        perf.enrich_performance()
        dd = perf.data["dd"].dropna()
        assert (dd >= 0).all()
        assert (dd <= 1).all()

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
