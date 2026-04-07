"""
Integration test: runs the full backtest pipeline with synthetic data.
data → StrategyConfig → Performance → ParametersOptimization → WalkForward
No external API calls are made.
"""

import os
import tempfile

import numpy as np
import pandas as pd
import pytest
from unittest.mock import patch, MagicMock

from strat import Strategy, StrategyConfig, SubStrategy, strategy_to_json, backtest_results_to_json
from perf import Performance
from param_opt import ParametersOptimization
from walk_forward import WalkForward, WalkForwardResult


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
        config = StrategyConfig("TEST", "get_sma", Strategy.momentum_const_signal, 252)
        perf = Performance(synthetic_market_data.copy(), config, 20, 0.5)
        perf.enrich_performance()
        result = perf.get_strategy_performance()
        assert isinstance(result, pd.Series)
        assert len(result) == 5
        assert np.isfinite(result["Total Return"])
        assert perf.get_max_drawdown() >= 0

    def test_ema_reversion_pipeline(self, synthetic_market_data):
        config = StrategyConfig("TEST", "get_ema", Strategy.reversion_const_signal, 252)
        perf = Performance(synthetic_market_data.copy(), config, 15, 1.0)
        perf.enrich_performance()
        result = perf.get_strategy_performance()
        assert isinstance(result, pd.Series)
        assert np.isfinite(result["Sharpe Ratio"])

    def test_bollinger_momentum_pipeline(self, synthetic_market_data):
        config = StrategyConfig("TEST", "get_bollinger_band", Strategy.momentum_const_signal, 252)
        perf = Performance(synthetic_market_data.copy(), config, 20, 1.0)
        perf.enrich_performance()
        strat_perf = perf.get_strategy_performance()
        bh_perf = perf.get_buy_hold_performance()
        assert isinstance(strat_perf, pd.Series)
        assert isinstance(bh_perf, pd.Series)
        # Both should return finite values for total return
        assert np.isfinite(strat_perf["Total Return"])
        assert np.isfinite(bh_perf["Total Return"])

    def test_rsi_momentum_pipeline(self, synthetic_market_data):
        config = StrategyConfig("TEST", "get_rsi", Strategy.momentum_const_signal, 252)
        perf = Performance(synthetic_market_data.copy(), config, 14, 30.0)
        perf.enrich_performance()
        result = perf.get_strategy_performance()
        assert isinstance(result, pd.Series)


class TestParameterOptimizationPipeline:
    """End-to-end test: data → indicators → grid search → Sharpe results."""

    def test_grid_search_produces_results(self, synthetic_market_data):
        config = StrategyConfig("TEST", "get_bollinger_band", Strategy.momentum_const_signal, 252)
        opt = ParametersOptimization(synthetic_market_data.copy(), config)
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
        config = StrategyConfig("TEST", "get_bollinger_band", Strategy.momentum_const_signal, 252)
        opt = ParametersOptimization(synthetic_market_data.copy(), config)
        results = pd.DataFrame(
            opt.optimize((10, 20), (0.5, 1.0)), columns=["window", "signal", "sharpe"]
        )
        pivot = results.pivot(index="window", columns="signal", values="sharpe")
        assert pivot.shape == (2, 2)
        assert not pivot.isna().any().any()


class TestStrategyVsBuyHoldConsistency:
    """Verify that strategy and buy-and-hold metrics are internally consistent."""

    def test_buy_hold_cumulative_matches_total_return(self, synthetic_market_data):
        config = StrategyConfig("TEST", "get_bollinger_band", Strategy.momentum_const_signal, 252)
        perf = Performance(synthetic_market_data.copy(), config, 20, 1.0)
        perf.enrich_performance()
        total = perf.get_buy_hold_total_return()
        cumu_last = perf.data["buy_hold_cumu"].iloc[-1]
        assert total == pytest.approx(cumu_last)

    def test_strategy_cumulative_matches_total_return(self, synthetic_market_data):
        config = StrategyConfig("TEST", "get_bollinger_band", Strategy.momentum_const_signal, 252)
        perf = Performance(synthetic_market_data.copy(), config, 20, 1.0)
        perf.enrich_performance()
        total = perf.get_total_return()
        cumu_last = perf.data["cumu"].iloc[-1]
        assert total == pytest.approx(cumu_last)

    def test_max_drawdown_within_cumulative_range(self, synthetic_market_data):
        config = StrategyConfig("TEST", "get_bollinger_band", Strategy.momentum_const_signal, 252)
        perf = Performance(synthetic_market_data.copy(), config, 20, 1.0)
        perf.enrich_performance()
        max_dd = perf.get_max_drawdown()
        cumu_range = perf.data["cumu"].max() - perf.data["cumu"].min()
        assert max_dd <= cumu_range + 1e-10


class TestRemainingIndicatorStrategyCombos:
    """Cover indicator × strategy combinations not tested in TestFullBacktestPipeline."""

    def test_sma_reversion_pipeline(self, synthetic_market_data):
        config = StrategyConfig("TEST", "get_sma", Strategy.reversion_const_signal, 252)
        perf = Performance(synthetic_market_data.copy(), config, 20, 0.5)
        perf.enrich_performance()
        result = perf.get_strategy_performance()
        assert isinstance(result, pd.Series)
        assert np.isfinite(result["Total Return"])

    def test_ema_momentum_pipeline(self, synthetic_market_data):
        config = StrategyConfig("TEST", "get_ema", Strategy.momentum_const_signal, 252)
        perf = Performance(synthetic_market_data.copy(), config, 15, 1.0)
        perf.enrich_performance()
        result = perf.get_strategy_performance()
        assert isinstance(result, pd.Series)
        assert np.isfinite(result["Total Return"])

    def test_bollinger_reversion_pipeline(self, synthetic_market_data):
        config = StrategyConfig("TEST", "get_bollinger_band", Strategy.reversion_const_signal, 252)
        perf = Performance(synthetic_market_data.copy(), config, 20, 1.0)
        perf.enrich_performance()
        result = perf.get_strategy_performance()
        assert isinstance(result, pd.Series)
        assert np.isfinite(result["Total Return"])

    def test_rsi_reversion_pipeline(self, synthetic_market_data):
        config = StrategyConfig("TEST", "get_rsi", Strategy.reversion_const_signal, 252)
        perf = Performance(synthetic_market_data.copy(), config, 14, 30.0)
        perf.enrich_performance()
        result = perf.get_strategy_performance()
        assert isinstance(result, pd.Series)
        assert np.isfinite(result["Total Return"])

    def test_stochastic_momentum_pipeline(self, synthetic_market_data):
        config = StrategyConfig("TEST", "get_stochastic_oscillator", Strategy.momentum_const_signal, 252)
        perf = Performance(synthetic_market_data.copy(), config, 14, 20.0)
        perf.enrich_performance()
        result = perf.get_strategy_performance()
        assert isinstance(result, pd.Series)

    def test_stochastic_reversion_pipeline(self, synthetic_market_data):
        config = StrategyConfig("TEST", "get_stochastic_oscillator", Strategy.reversion_const_signal, 252)
        perf = Performance(synthetic_market_data.copy(), config, 14, 20.0)
        perf.enrich_performance()
        result = perf.get_strategy_performance()
        assert isinstance(result, pd.Series)


class TestTransactionCostPipeline:
    """Verify transaction fees propagate correctly through the pipeline."""

    def test_higher_fees_reduce_returns(self, synthetic_market_data):
        config = StrategyConfig("TEST", "get_bollinger_band", Strategy.momentum_const_signal, 252)
        perf_zero = Performance(
            synthetic_market_data.copy(), config, 20, 1.0, fee_bps=0,
        )
        perf_zero.enrich_performance()
        perf_high = Performance(
            synthetic_market_data.copy(), config, 20, 1.0, fee_bps=50,
        )
        perf_high.enrich_performance()
        assert perf_zero.get_total_return() >= perf_high.get_total_return()

    def test_zero_fee_no_cost_deducted(self, synthetic_market_data):
        config = StrategyConfig("TEST", "get_bollinger_band", Strategy.momentum_const_signal, 252)
        perf = Performance(
            synthetic_market_data.copy(), config, 20, 1.0, fee_bps=0,
        )
        perf.enrich_performance()
        # With zero fees, pnl = position_x1 * chg (no cost adjustment)
        expected_pnl = perf.data["FinalPosition_x1"] * perf.data["chg"]
        pd.testing.assert_series_equal(
            perf.data["pnl"].dropna(), expected_pnl.dropna(), check_names=False,
        )

    def test_fee_propagates_to_param_opt(self, synthetic_market_data):
        config = StrategyConfig("TEST", "get_bollinger_band", Strategy.momentum_const_signal, 252)
        opt_zero = ParametersOptimization(
            synthetic_market_data.copy(), config, fee_bps=0,
        )
        results_zero = pd.DataFrame(
            opt_zero.optimize((20,), (1.0,)), columns=["window", "signal", "sharpe"]
        )

        opt_high = ParametersOptimization(
            synthetic_market_data.copy(), config, fee_bps=50,
        )
        results_high = pd.DataFrame(
            opt_high.optimize((20,), (1.0,)), columns=["window", "signal", "sharpe"]
        )

        # Higher fees should produce lower or equal Sharpe
        assert results_zero.iloc[0]["sharpe"] >= results_high.iloc[0]["sharpe"]


class TestTradingPeriodVariants:
    """Verify annualization differences between crypto (365) and equity (252)."""

    def test_crypto_vs_equity_sharpe_differs(self, synthetic_market_data):
        config_crypto = StrategyConfig("TEST", "get_bollinger_band", Strategy.momentum_const_signal, 365)
        perf_crypto = Performance(synthetic_market_data.copy(), config_crypto, 20, 1.0)
        perf_crypto.enrich_performance()

        config_equity = StrategyConfig("TEST", "get_bollinger_band", Strategy.momentum_const_signal, 252)
        perf_equity = Performance(synthetic_market_data.copy(), config_equity, 20, 1.0)
        perf_equity.enrich_performance()

        # Same daily data but different annualization → different Sharpe
        sharpe_crypto = perf_crypto.get_sharpe_ratio()
        sharpe_equity = perf_equity.get_sharpe_ratio()
        assert sharpe_crypto != pytest.approx(sharpe_equity)

    def test_crypto_annualized_return_uses_365(self, synthetic_market_data):
        config = StrategyConfig("TEST", "get_bollinger_band", Strategy.momentum_const_signal, 365)
        perf = Performance(synthetic_market_data.copy(), config, 20, 1.0)
        perf.enrich_performance()
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
        config = StrategyConfig("TEST", "get_bollinger_band", Strategy.momentum_const_signal, 252)
        perf = Performance(df, config, 20, 1.0)
        perf.enrich_performance()
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
        config = StrategyConfig("TEST", "get_sma", Strategy.momentum_const_signal, 252)
        perf = Performance(df, config, 10, 0.5)
        perf.enrich_performance()
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
        config = StrategyConfig("TEST", "get_bollinger_band", Strategy.momentum_const_signal, 252)
        perf = Performance(df, config, 20, 1.0)
        perf.enrich_performance()
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


class TestWalkForwardPipeline:
    """Integration test: walk-forward overfitting detection with synthetic data."""

    def test_walk_forward_full_pipeline(self, synthetic_market_data):
        config = StrategyConfig("TEST", "get_bollinger_band", Strategy.momentum_const_signal, 252)
        wf = WalkForward(synthetic_market_data.copy(), 0.5, config)
        result = wf.run((10, 20, 30), (0.5, 1.0, 1.5))

        assert isinstance(result, WalkForwardResult)
        assert result.best_window in (10, 20, 30)
        assert result.best_signal in (0.5, 1.0, 1.5)
        assert isinstance(result.is_metrics, pd.Series)
        assert isinstance(result.oos_metrics, pd.Series)

    def test_walk_forward_summary_table(self, synthetic_market_data):
        config = StrategyConfig("TEST", "get_bollinger_band", Strategy.momentum_const_signal, 252)
        wf = WalkForward(synthetic_market_data.copy(), 0.5, config)
        result = wf.run((20,), (1.0,))
        summary = result.summary()

        assert isinstance(summary, pd.DataFrame)
        assert "In-Sample" in summary.columns
        assert "Out-of-Sample" in summary.columns
        assert "Overfitting Ratio" in summary.index

    def test_walk_forward_with_different_splits(self, synthetic_market_data):
        """Different split ratios should produce different in-sample sizes."""
        config = StrategyConfig("TEST", "get_bollinger_band", Strategy.momentum_const_signal, 252)
        results = {}
        for ratio in (0.3, 0.5, 0.7):
            wf = WalkForward(synthetic_market_data.copy(), ratio, config)
            results[ratio] = wf.run((20,), (1.0,))

        # All should complete without error
        for ratio, result in results.items():
            assert isinstance(result, WalkForwardResult)

    def test_walk_forward_with_fees(self, synthetic_market_data):
        config = StrategyConfig("TEST", "get_bollinger_band", Strategy.momentum_const_signal, 252)
        wf_no_fee = WalkForward(
            synthetic_market_data.copy(), 0.5, config, fee_bps=0,
        )
        result_no_fee = wf_no_fee.run((20,), (1.0,))

        wf_fee = WalkForward(
            synthetic_market_data.copy(), 0.5, config, fee_bps=50,
        )
        result_fee = wf_fee.run((20,), (1.0,))

        # Higher fees should reduce in-sample total return
        assert result_no_fee.is_metrics["Total Return"] >= result_fee.is_metrics["Total Return"]

    def test_walk_forward_crypto_period(self, synthetic_market_data):
        """Walk-forward should work with crypto trading period (365)."""
        config = StrategyConfig("TEST", "get_bollinger_band", Strategy.momentum_const_signal, 365)
        wf = WalkForward(synthetic_market_data.copy(), 0.5, config)
        result = wf.run((20,), (1.0,))
        assert isinstance(result, WalkForwardResult)
        assert np.isfinite(result.is_metrics["Annualized Return"])

    def test_walk_forward_cli_produces_output(self, synthetic_market_data):
        """CLI main() with --walk-forward produces wf_ CSV."""
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
                    "--no-grid",
                    "--walk-forward",
                    "--split", "0.5",
                    "--win-min", "10",
                    "--win-max", "20",
                    "--win-step", "10",
                    "--sig-min", "0.5",
                    "--sig-max", "1.0",
                    "--sig-step", "0.5",
                    "--outdir", tmpdir,
                ])
                main(args)

            wf_file = os.path.join(tmpdir, "wf_test_bollinger.csv")
            assert os.path.isfile(wf_file)
            wf_df = pd.read_csv(wf_file)
            assert "In-Sample" in wf_df.columns
            assert "Out-of-Sample" in wf_df.columns


class TestStrategyConfigPipeline:
    """Integration test: full pipeline using StrategyConfig directly."""

    def test_config_full_pipeline(self, synthetic_market_data):
        config = StrategyConfig("TEST", "get_bollinger_band",
                                Strategy.momentum_const_signal, 252)
        perf = Performance(synthetic_market_data.copy(), config, 20, 1.0)
        perf.enrich_performance()
        result = perf.get_strategy_performance()
        assert isinstance(result, pd.Series)
        assert len(result) == 5
        assert np.isfinite(result["Total Return"])

    def test_config_grid_search(self, synthetic_market_data):
        config = StrategyConfig("TEST", "get_bollinger_band",
                                Strategy.momentum_const_signal, 252)
        opt = ParametersOptimization(synthetic_market_data.copy(), config)
        results = pd.DataFrame(
            opt.optimize((10, 20), (0.5, 1.0)),
            columns=["window", "signal", "sharpe"],
        )
        assert len(results) == 4
        assert results["sharpe"].notna().all()

    def test_config_walk_forward(self, synthetic_market_data):
        config = StrategyConfig("TEST", "get_bollinger_band",
                                Strategy.momentum_const_signal, 252)
        wf = WalkForward(synthetic_market_data.copy(), 0.5, config)
        result = wf.run((10, 20), (0.5, 1.0))
        assert isinstance(result, WalkForwardResult)
        assert result.best_window in (10, 20)

    def test_config_reusable_across_calls(self, synthetic_market_data):
        """Same config reused for perf, opt, and walk-forward."""
        config = StrategyConfig("TEST", "get_sma",
                                Strategy.reversion_const_signal, 365)

        perf = Performance(synthetic_market_data.copy(), config, 20, 0.5)
        perf.enrich_performance()
        assert isinstance(perf.get_strategy_performance(), pd.Series)

        opt = ParametersOptimization(synthetic_market_data.copy(), config)
        results = list(opt.optimize((20,), (0.5,)))
        assert len(results) == 1

        wf = WalkForward(synthetic_market_data.copy(), 0.5, config)
        wf_result = wf.run((20,), (0.5,))
        assert isinstance(wf_result, WalkForwardResult)


class TestStrategyConfigSinglePipeline:
    """Integration test: StrategyConfig.single() through full pipeline."""

    def test_single_config_runs_pipeline(self, synthetic_market_data):
        cfg = StrategyConfig.single(
            "TEST", "get_bollinger_band",
            Strategy.momentum_const_signal, 252,
            window=20, signal=1.0
        )
        perf = Performance(synthetic_market_data.copy(), cfg, 20, 1.0)
        perf.enrich_performance()
        result = perf.get_strategy_performance()
        assert isinstance(result, pd.Series)
        assert np.isfinite(result["Total Return"])

    def test_single_config_matches_legacy(self, synthetic_market_data):
        """StrategyConfig.single() should produce identical perf as legacy constructor."""
        legacy = StrategyConfig("TEST", "get_bollinger_band",
                                Strategy.momentum_const_signal, 252,
                                strategy_id="same")
        single = StrategyConfig.single(
            "TEST", "get_bollinger_band",
            Strategy.momentum_const_signal, 252,
            window=20, signal=1.0, strategy_id="same"
        )
        perf_legacy = Performance(synthetic_market_data.copy(), legacy, 20, 1.0)
        perf_legacy.enrich_performance()
        perf_single = Performance(synthetic_market_data.copy(), single, 20, 1.0)
        perf_single.enrich_performance()
        pd.testing.assert_series_equal(
            perf_legacy.get_strategy_performance(),
            perf_single.get_strategy_performance(),
        )

    def test_single_config_grid_search(self, synthetic_market_data):
        cfg = StrategyConfig.single(
            "TEST", "get_sma", Strategy.reversion_const_signal, 252,
            window=20, signal=0.5
        )
        opt = ParametersOptimization(synthetic_market_data.copy(), cfg)
        results = pd.DataFrame(
            opt.optimize((10, 20), (0.5, 1.0)),
            columns=["window", "signal", "sharpe"],
        )
        assert len(results) == 4


class TestJsonSerializationPipeline:
    """Integration test: JSON serialization round-trip through the pipeline."""

    def test_strategy_to_json_after_backtest(self, synthetic_market_data):
        cfg = StrategyConfig.single(
            "BTC-USD", "get_bollinger_band",
            Strategy.momentum_const_signal, 365,
            window=20, signal=1.0, strategy_id="json-test"
        )
        perf = Performance(synthetic_market_data.copy(), cfg, 20, 1.0)
        perf.enrich_performance()
        strat_json = strategy_to_json(cfg)
        bt_json = backtest_results_to_json(
            cfg.strategy_id, perf, cfg.ticker,
            "2020-01-01", "2023-12-31", 5.0
        )
        # strategy_id links both records
        assert strat_json["strategy_id"] == bt_json["strategy_id"]
        assert strat_json["ticker"] == "BTC-USD"
        assert bt_json["ticker_backtested"] == "BTC-USD"
        assert bt_json["metrics"]["Total Return"] == pytest.approx(
            perf.get_total_return()
        )

    def test_multi_substrategy_json(self):
        sub1 = SubStrategy("get_sma", "momentum_const_signal", 20, 1.0)
        sub2 = SubStrategy("get_rsi", "reversion_const_signal", 14, 0.5)
        cfg = StrategyConfig(
            "AAPL", "get_sma", Strategy.momentum_const_signal, 252,
            strategy_id="multi-json", conjunction="OR",
            substrategies=(sub1, sub2)
        )
        result = strategy_to_json(cfg)
        assert result["conjunction"] == "OR"
        assert len(result["substrategies"]) == 2
        assert result["substrategies"][0]["indicator"] == "get_sma"
        assert result["substrategies"][1]["indicator"] == "get_rsi"


# -------------------------------------------------------------------------
# Phase 3: Multi-factor pipeline integration
# -------------------------------------------------------------------------

class TestMultiFactorPipeline:
    """End-to-end: multi-factor StrategyConfig → Performance → metrics."""

    @pytest.fixture
    def multi_factor_market_data(self):
        np.random.seed(99)
        n = 300
        close = 100 + np.cumsum(np.random.randn(n) * 0.5)
        volume = 5000 + np.cumsum(np.random.randn(n) * 100)
        return pd.DataFrame({
            "price": close,
            "factor": close,
            "v": close,
            "volume": volume,
            "Close": close,
            "High": close + np.abs(np.random.randn(n) * 0.3),
            "Low": close - np.abs(np.random.randn(n) * 0.3),
        })

    def test_two_factor_and_pipeline(self, multi_factor_market_data):
        sub_a = SubStrategy("get_sma", "momentum_const_signal", 10, 0.5, "v")
        sub_b = SubStrategy("get_sma", "momentum_const_signal", 20, 0.5, "volume")
        config = StrategyConfig(
            "TEST", "get_sma", Strategy.momentum_const_signal, 252,
            conjunction="AND", substrategies=(sub_a, sub_b),
        )
        perf = Performance(multi_factor_market_data.copy(), config)
        perf.enrich_performance()
        result = perf.get_strategy_performance()
        assert isinstance(result, pd.Series)
        assert len(result) == 5
        assert np.isfinite(result["Total Return"])
        assert perf.get_max_drawdown() >= 0
        # Per-factor columns present
        for col in ["factor1", "indicator1", "position1",
                     "factor2", "indicator2", "position2",
                     "FinalPosition", "FinalPosition_x1"]:
            assert col in perf.data.columns, f"Missing column: {col}"
        sub_a = SubStrategy("get_sma", "momentum_const_signal", 10, 0.5, "v")
        sub_b = SubStrategy("get_sma", "momentum_const_signal", 20, 0.5, "volume")
        config = StrategyConfig(
            "TEST", "get_sma", Strategy.momentum_const_signal, 252,
            conjunction="OR", substrategies=(sub_a, sub_b),
        )
        perf = Performance(multi_factor_market_data.copy(), config)
        perf.enrich_performance()
        result = perf.get_strategy_performance()
        assert isinstance(result, pd.Series)
        bh = perf.get_buy_hold_performance()
        assert isinstance(bh, pd.Series)

    def test_multi_factor_buy_hold_unaffected(self, multi_factor_market_data):
        """Buy-and-hold metrics should be the same regardless of conjunction."""
        sub_a = SubStrategy("get_sma", "momentum_const_signal", 10, 0.5, "v")
        sub_b = SubStrategy("get_sma", "momentum_const_signal", 20, 0.5, "volume")
        config_and = StrategyConfig(
            "TEST", "get_sma", Strategy.momentum_const_signal, 252,
            conjunction="AND", substrategies=(sub_a, sub_b),
        )
        config_or = StrategyConfig(
            "TEST", "get_sma", Strategy.momentum_const_signal, 252,
            conjunction="OR", substrategies=(sub_a, sub_b),
        )
        perf_and = Performance(multi_factor_market_data.copy(), config_and)
        perf_and.enrich_performance()
        perf_or = Performance(multi_factor_market_data.copy(), config_or)
        perf_or.enrich_performance()
        assert perf_and.get_buy_hold_total_return() == pytest.approx(
            perf_or.get_buy_hold_total_return(), abs=1e-10
        )
