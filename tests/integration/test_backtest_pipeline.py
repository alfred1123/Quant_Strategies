"""
Integration test: runs the full backtest pipeline with synthetic data.
data → TechnicalAnalysis → Strategy → Performance → ParametersOptimization
No external API calls are made.
"""

import os
import tempfile

import numpy as np
import pandas as pd
import pytest
from unittest.mock import patch, MagicMock

from ta import TechnicalAnalysis
from strat import Strategy
from perf import Performance
from param_opt import ParametersOptimization


@pytest.fixture
def synthetic_market_data():
    """Generate realistic synthetic OHLCV data with a trend + noise."""
    np.random.seed(123)
    n = 500
    trend = np.linspace(100, 150, n)
    noise = np.cumsum(np.random.randn(n) * 0.3)
    close = trend + noise
    high = close + np.abs(np.random.randn(n) * 0.5)
    low = close - np.abs(np.random.randn(n) * 0.5)
    return pd.DataFrame({
        "price": close,
        "factor": close,
        "Close": close,
        "High": high,
        "Low": low,
    })


class TestFullBacktestPipeline:
    """End-to-end test: data → indicators → strategy → performance."""

    def test_sma_momentum_pipeline(self, synthetic_market_data):
        df = synthetic_market_data.copy()
        ta = TechnicalAnalysis(df)
        perf = Performance(
            ta.data, 252, ta.get_sma, Strategy.momentum_const_signal, 20, 0.5
        )
        result = perf.get_strategy_performance()
        assert isinstance(result, pd.Series)
        assert len(result) == 5
        assert np.isfinite(result["Total Return"])
        assert perf.get_max_drawdown() >= 0

    def test_ema_reversion_pipeline(self, synthetic_market_data):
        df = synthetic_market_data.copy()
        ta = TechnicalAnalysis(df)
        perf = Performance(
            ta.data, 252, ta.get_ema, Strategy.reversion_const_signal, 15, 1.0
        )
        result = perf.get_strategy_performance()
        assert isinstance(result, pd.Series)
        assert np.isfinite(result["Sharpe Ratio"])

    def test_bollinger_momentum_pipeline(self, synthetic_market_data):
        df = synthetic_market_data.copy()
        ta = TechnicalAnalysis(df)
        perf = Performance(
            ta.data, 252, ta.get_bollinger_band, Strategy.momentum_const_signal, 20, 1.0
        )
        strat_perf = perf.get_strategy_performance()
        bh_perf = perf.get_buy_hold_performance()
        assert isinstance(strat_perf, pd.Series)
        assert isinstance(bh_perf, pd.Series)
        # Both should return finite values for total return
        assert np.isfinite(strat_perf["Total Return"])
        assert np.isfinite(bh_perf["Total Return"])

    def test_rsi_momentum_pipeline(self, synthetic_market_data):
        df = synthetic_market_data.copy()
        ta = TechnicalAnalysis(df)
        perf = Performance(
            ta.data, 252, ta.get_rsi, Strategy.momentum_const_signal, 14, 30.0
        )
        result = perf.get_strategy_performance()
        assert isinstance(result, pd.Series)


class TestParameterOptimizationPipeline:
    """End-to-end test: data → indicators → grid search → Sharpe results."""

    def test_grid_search_produces_results(self, synthetic_market_data):
        df = synthetic_market_data.copy()
        ta = TechnicalAnalysis(df)
        opt = ParametersOptimization(
            ta.data, 252, ta.get_bollinger_band, Strategy.momentum_const_signal
        )
        windows = (10, 20, 30)
        signals = (0.5, 1.0, 1.5)
        results = pd.DataFrame(
            opt.optimize(windows, signals), columns=["window", "signal", "sharpe"]
        )
        assert len(results) == 9
        assert results["window"].nunique() == 3
        assert results["signal"].nunique() == 3
        assert results["sharpe"].notna().all()

    def test_grid_search_can_pivot_to_heatmap(self, synthetic_market_data):
        df = synthetic_market_data.copy()
        ta = TechnicalAnalysis(df)
        opt = ParametersOptimization(
            ta.data, 252, ta.get_bollinger_band, Strategy.momentum_const_signal
        )
        results = pd.DataFrame(
            opt.optimize((10, 20), (0.5, 1.0)), columns=["window", "signal", "sharpe"]
        )
        pivot = results.pivot(index="window", columns="signal", values="sharpe")
        assert pivot.shape == (2, 2)
        assert not pivot.isna().any().any()


class TestStrategyVsBuyHoldConsistency:
    """Verify that strategy and buy-and-hold metrics are internally consistent."""

    def test_buy_hold_cumulative_matches_total_return(self, synthetic_market_data):
        df = synthetic_market_data.copy()
        ta = TechnicalAnalysis(df)
        perf = Performance(
            ta.data, 252, ta.get_bollinger_band, Strategy.momentum_const_signal, 20, 1.0
        )
        total = perf.get_buy_hold_total_return()
        cumu_last = perf.data["buy_hold_cumu"].iloc[-1]
        assert total == pytest.approx(cumu_last)

    def test_strategy_cumulative_matches_total_return(self, synthetic_market_data):
        df = synthetic_market_data.copy()
        ta = TechnicalAnalysis(df)
        perf = Performance(
            ta.data, 252, ta.get_bollinger_band, Strategy.momentum_const_signal, 20, 1.0
        )
        total = perf.get_total_return()
        cumu_last = perf.data["cumu"].iloc[-1]
        assert total == pytest.approx(cumu_last)

    def test_max_drawdown_within_cumulative_range(self, synthetic_market_data):
        df = synthetic_market_data.copy()
        ta = TechnicalAnalysis(df)
        perf = Performance(
            ta.data, 252, ta.get_bollinger_band, Strategy.momentum_const_signal, 20, 1.0
        )
        max_dd = perf.get_max_drawdown()
        cumu_range = perf.data["cumu"].max() - perf.data["cumu"].min()
        assert max_dd <= cumu_range + 1e-10


class TestRemainingIndicatorStrategyCombos:
    """Cover indicator × strategy combinations not tested in TestFullBacktestPipeline."""

    def test_sma_reversion_pipeline(self, synthetic_market_data):
        df = synthetic_market_data.copy()
        ta = TechnicalAnalysis(df)
        perf = Performance(
            ta.data, 252, ta.get_sma, Strategy.reversion_const_signal, 20, 0.5
        )
        result = perf.get_strategy_performance()
        assert isinstance(result, pd.Series)
        assert np.isfinite(result["Total Return"])

    def test_ema_momentum_pipeline(self, synthetic_market_data):
        df = synthetic_market_data.copy()
        ta = TechnicalAnalysis(df)
        perf = Performance(
            ta.data, 252, ta.get_ema, Strategy.momentum_const_signal, 15, 1.0
        )
        result = perf.get_strategy_performance()
        assert isinstance(result, pd.Series)
        assert np.isfinite(result["Total Return"])

    def test_bollinger_reversion_pipeline(self, synthetic_market_data):
        df = synthetic_market_data.copy()
        ta = TechnicalAnalysis(df)
        perf = Performance(
            ta.data, 252, ta.get_bollinger_band, Strategy.reversion_const_signal, 20, 1.0
        )
        result = perf.get_strategy_performance()
        assert isinstance(result, pd.Series)
        assert np.isfinite(result["Total Return"])

    def test_rsi_reversion_pipeline(self, synthetic_market_data):
        df = synthetic_market_data.copy()
        ta = TechnicalAnalysis(df)
        perf = Performance(
            ta.data, 252, ta.get_rsi, Strategy.reversion_const_signal, 14, 30.0
        )
        result = perf.get_strategy_performance()
        assert isinstance(result, pd.Series)
        assert np.isfinite(result["Total Return"])

    def test_stochastic_momentum_pipeline(self, synthetic_market_data):
        df = synthetic_market_data.copy()
        ta = TechnicalAnalysis(df)
        perf = Performance(
            ta.data, 252, ta.get_stochastic_oscillator,
            Strategy.momentum_const_signal, 14, 20.0
        )
        result = perf.get_strategy_performance()
        assert isinstance(result, pd.Series)

    def test_stochastic_reversion_pipeline(self, synthetic_market_data):
        df = synthetic_market_data.copy()
        ta = TechnicalAnalysis(df)
        perf = Performance(
            ta.data, 252, ta.get_stochastic_oscillator,
            Strategy.reversion_const_signal, 14, 20.0
        )
        result = perf.get_strategy_performance()
        assert isinstance(result, pd.Series)


class TestTransactionCostPipeline:
    """Verify transaction fees propagate correctly through the pipeline."""

    def test_higher_fees_reduce_returns(self, synthetic_market_data):
        df_zero = synthetic_market_data.copy()
        ta_zero = TechnicalAnalysis(df_zero)
        perf_zero = Performance(
            ta_zero.data, 252, ta_zero.get_bollinger_band,
            Strategy.momentum_const_signal, 20, 1.0, fee_bps=0,
        )

        df_high = synthetic_market_data.copy()
        ta_high = TechnicalAnalysis(df_high)
        perf_high = Performance(
            ta_high.data, 252, ta_high.get_bollinger_band,
            Strategy.momentum_const_signal, 20, 1.0, fee_bps=50,
        )

        assert perf_zero.get_total_return() >= perf_high.get_total_return()

    def test_zero_fee_no_cost_deducted(self, synthetic_market_data):
        df = synthetic_market_data.copy()
        ta = TechnicalAnalysis(df)
        perf = Performance(
            ta.data, 252, ta.get_bollinger_band,
            Strategy.momentum_const_signal, 20, 1.0, fee_bps=0,
        )
        # With zero fees, pnl = position_x1 * chg (no cost adjustment)
        expected_pnl = perf.data["position_x1"] * perf.data["chg"]
        pd.testing.assert_series_equal(
            perf.data["pnl"].dropna(), expected_pnl.dropna(), check_names=False,
        )

    def test_fee_propagates_to_param_opt(self, synthetic_market_data):
        df_zero = synthetic_market_data.copy()
        ta_zero = TechnicalAnalysis(df_zero)
        opt_zero = ParametersOptimization(
            ta_zero.data, 252, ta_zero.get_bollinger_band,
            Strategy.momentum_const_signal, fee_bps=0,
        )
        results_zero = pd.DataFrame(
            opt_zero.optimize((20,), (1.0,)), columns=["window", "signal", "sharpe"]
        )

        df_high = synthetic_market_data.copy()
        ta_high = TechnicalAnalysis(df_high)
        opt_high = ParametersOptimization(
            ta_high.data, 252, ta_high.get_bollinger_band,
            Strategy.momentum_const_signal, fee_bps=50,
        )
        results_high = pd.DataFrame(
            opt_high.optimize((20,), (1.0,)), columns=["window", "signal", "sharpe"]
        )

        # Higher fees should produce lower or equal Sharpe
        assert results_zero.iloc[0]["sharpe"] >= results_high.iloc[0]["sharpe"]


class TestTradingPeriodVariants:
    """Verify annualization differences between crypto (365) and equity (252)."""

    def test_crypto_vs_equity_sharpe_differs(self, synthetic_market_data):
        df_crypto = synthetic_market_data.copy()
        ta_crypto = TechnicalAnalysis(df_crypto)
        perf_crypto = Performance(
            ta_crypto.data, 365, ta_crypto.get_bollinger_band,
            Strategy.momentum_const_signal, 20, 1.0
        )

        df_equity = synthetic_market_data.copy()
        ta_equity = TechnicalAnalysis(df_equity)
        perf_equity = Performance(
            ta_equity.data, 252, ta_equity.get_bollinger_band,
            Strategy.momentum_const_signal, 20, 1.0
        )

        # Same daily data but different annualization → different Sharpe
        sharpe_crypto = perf_crypto.get_sharpe_ratio()
        sharpe_equity = perf_equity.get_sharpe_ratio()
        assert sharpe_crypto != pytest.approx(sharpe_equity)

    def test_crypto_annualized_return_uses_365(self, synthetic_market_data):
        df = synthetic_market_data.copy()
        ta = TechnicalAnalysis(df)
        perf = Performance(
            ta.data, 365, ta.get_bollinger_band,
            Strategy.momentum_const_signal, 20, 1.0
        )
        ann_ret = perf.get_annualized_return()
        daily_mean = perf.data.loc[20:len(perf.data) - 1, "pnl"].mean()
        assert ann_ret == pytest.approx(daily_mean * 365)


class TestEdgeCases:
    """Pipeline behaviour under edge-case data conditions."""

    def test_short_data_window_near_length(self):
        """Window = 20 with only 30 rows — very few valid signals."""
        np.random.seed(99)
        n = 30
        prices = 100 + np.cumsum(np.random.randn(n) * 0.5)
        df = pd.DataFrame({
            "price": prices, "factor": prices, "Close": prices,
            "High": prices + 1, "Low": prices - 1,
        })
        ta = TechnicalAnalysis(df)
        perf = Performance(
            ta.data, 252, ta.get_bollinger_band,
            Strategy.momentum_const_signal, 20, 1.0
        )
        result = perf.get_strategy_performance()
        assert isinstance(result, pd.Series)
        assert len(result) == 5

    def test_flat_price_zero_pnl(self):
        """Constant price → zero pnl, NaN Sharpe."""
        n = 100
        prices = np.full(n, 100.0)
        df = pd.DataFrame({
            "price": prices, "factor": prices, "Close": prices,
            "High": prices, "Low": prices,
        })
        ta = TechnicalAnalysis(df)
        perf = Performance(
            ta.data, 252, ta.get_sma,
            Strategy.momentum_const_signal, 10, 0.5
        )
        # No price change → zero PnL
        assert perf.get_total_return() == pytest.approx(0.0)
        assert perf.get_buy_hold_total_return() == pytest.approx(0.0)

    def test_extreme_volatility_no_crash(self):
        """Large price swings should not raise exceptions."""
        np.random.seed(77)
        n = 200
        prices = 100 + np.cumsum(np.random.randn(n) * 10)
        prices = np.abs(prices) + 1  # keep positive
        df = pd.DataFrame({
            "price": prices, "factor": prices, "Close": prices,
            "High": prices + 5, "Low": prices - 5,
        })
        ta = TechnicalAnalysis(df)
        perf = Performance(
            ta.data, 252, ta.get_bollinger_band,
            Strategy.momentum_const_signal, 20, 1.0
        )
        result = perf.get_strategy_performance()
        assert isinstance(result, pd.Series)
        assert perf.get_max_drawdown() >= 0


class TestCLIMainIntegration:
    """Integration test for main() with mocked YahooFinance data."""

    def test_main_produces_output_files(self, synthetic_market_data):
        mock_price = pd.DataFrame({
            "t": [f"2021-01-{i+1:02d}" for i in range(len(synthetic_market_data))],
            "v": synthetic_market_data["price"].values,
        })

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("main.YahooFinance") as mock_yf_cls:
                mock_yf = MagicMock()
                mock_yf.get_historical_price.return_value = mock_price
                mock_yf_cls.return_value = mock_yf

                from main import main, parse_args
                args = parse_args([
                    "--symbol", "TEST",
                    "--indicator", "bollinger",
                    "--strategy", "momentum",
                    "--window", "20",
                    "--signal", "1.0",
                    "--no-grid",
                    "--outdir", tmpdir,
                ])
                main(args)

            # Verify output CSV was created
            perf_file = os.path.join(tmpdir, "perf_test_bollinger.csv")
            assert os.path.isfile(perf_file)

            result_df = pd.read_csv(perf_file)
            for col in ["pnl", "cumu", "dd", "buy_hold", "buy_hold_cumu"]:
                assert col in result_df.columns

    def test_main_with_grid_search_produces_heatmap(self, synthetic_market_data):
        mock_price = pd.DataFrame({
            "t": [f"2021-01-{i+1:02d}" for i in range(len(synthetic_market_data))],
            "v": synthetic_market_data["price"].values,
        })

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("main.YahooFinance") as mock_yf_cls:
                mock_yf = MagicMock()
                mock_yf.get_historical_price.return_value = mock_price
                mock_yf_cls.return_value = mock_yf

                from main import main, parse_args
                args = parse_args([
                    "--symbol", "TEST",
                    "--indicator", "bollinger",
                    "--strategy", "momentum",
                    "--window", "20",
                    "--signal", "1.0",
                    "--win-min", "10",
                    "--win-max", "20",
                    "--win-step", "10",
                    "--sig-min", "0.5",
                    "--sig-max", "1.0",
                    "--sig-step", "0.5",
                    "--outdir", tmpdir,
                ])
                main(args)

            perf_file = os.path.join(tmpdir, "perf_test_bollinger.csv")
            opt_file = os.path.join(tmpdir, "opt_test_bollinger.csv")
            heatmap_file = os.path.join(tmpdir, "heatmap_test_bollinger.png")

            assert os.path.isfile(perf_file)
            assert os.path.isfile(opt_file)
            assert os.path.isfile(heatmap_file)

            opt_df = pd.read_csv(opt_file)
            assert list(opt_df.columns) == ["window", "signal", "sharpe"]
            assert len(opt_df) == 4  # 2 windows × 2 signals
