import pytest

from main import parse_args, INDICATORS, STRATEGIES, ASSET_TRADING_PERIODS


class TestParseArgsDefaults:
    def test_defaults(self):
        args = parse_args([])
        assert args.symbol == "BTC-USD"
        assert args.start == "2016-01-01"
        assert args.end == "2026-04-01"
        assert args.asset == "crypto"
        assert args.indicator == "bollinger"
        assert args.strategy == "momentum"
        assert args.window == 20
        assert args.signal == 1.0
        assert args.no_grid is False
        assert args.win_min == 5
        assert args.win_max == 100
        assert args.win_step == 5
        assert args.sig_min == 0.25
        assert args.sig_max == 2.50
        assert args.sig_step == 0.25
        assert args.outdir == "../results"
        assert args.fee == 5.0

    def test_custom_symbol(self):
        args = parse_args(["--symbol", "AAPL"])
        assert args.symbol == "AAPL"

    def test_asset_equity(self):
        args = parse_args(["--asset", "equity"])
        assert args.asset == "equity"

    def test_asset_invalid_rejected(self):
        with pytest.raises(SystemExit):
            parse_args(["--asset", "forex"])

    def test_indicator_choices(self):
        for ind in INDICATORS:
            args = parse_args(["--indicator", ind])
            assert args.indicator == ind

    def test_indicator_invalid_rejected(self):
        with pytest.raises(SystemExit):
            parse_args(["--indicator", "macd"])

    def test_strategy_choices(self):
        for strat in STRATEGIES:
            args = parse_args(["--strategy", strat])
            assert args.strategy == strat

    def test_strategy_invalid_rejected(self):
        with pytest.raises(SystemExit):
            parse_args(["--strategy", "random"])

    def test_no_grid_flag(self):
        args = parse_args(["--no-grid"])
        assert args.no_grid is True

    def test_custom_grid_bounds(self):
        args = parse_args([
            "--win-min", "10", "--win-max", "50", "--win-step", "10",
            "--sig-min", "0.5", "--sig-max", "2.0", "--sig-step", "0.5",
        ])
        assert args.win_min == 10
        assert args.win_max == 50
        assert args.win_step == 10
        assert args.sig_min == pytest.approx(0.5)
        assert args.sig_max == pytest.approx(2.0)
        assert args.sig_step == pytest.approx(0.5)

    def test_custom_fee(self):
        args = parse_args(["--fee", "10.0"])
        assert args.fee == pytest.approx(10.0)

    def test_verbose_flag(self):
        args = parse_args(["-v"])
        assert args.verbose is True

    def test_custom_dates(self):
        args = parse_args(["--start", "2020-01-01", "--end", "2025-01-01"])
        assert args.start == "2020-01-01"
        assert args.end == "2025-01-01"


class TestRegistries:
    def test_indicators_registry_keys(self):
        expected = {"bollinger", "sma", "ema", "rsi"}
        assert set(INDICATORS.keys()) == expected

    def test_indicators_registry_values_are_method_names(self):
        for key, method_name in INDICATORS.items():
            assert isinstance(method_name, str)
            assert method_name.startswith("get_")

    def test_strategies_registry_keys(self):
        expected = {"momentum", "reversion"}
        assert set(STRATEGIES.keys()) == expected

    def test_strategies_registry_values_are_callable(self):
        for key, func in STRATEGIES.items():
            assert callable(func)

    def test_asset_trading_periods_keys(self):
        expected = {"crypto", "equity"}
        assert set(ASSET_TRADING_PERIODS.keys()) == expected

    def test_asset_trading_periods_crypto(self):
        assert ASSET_TRADING_PERIODS["crypto"] == 365

    def test_asset_trading_periods_equity(self):
        assert ASSET_TRADING_PERIODS["equity"] == 252
