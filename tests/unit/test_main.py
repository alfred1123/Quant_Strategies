"""``quant.cli`` — argument parsing, and REFDATA as the only source of names."""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

import quant.cli as cli
from quant.cli import _grid_axes, main, parse_args
from quant.strategy.signals import SignalDirection

REQUIRED = ["--indicator", "bollinger", "--strategy", "momentum", "--asset", "crypto"]


class TestParseArgs:
    def test_defaults(self):
        args = parse_args(REQUIRED)
        assert args.symbol == "BTC-USD"
        assert args.start == "2016-01-01"
        assert args.end == "2026-04-01"
        assert args.window == 20
        assert args.signal == 1.0
        assert args.no_grid is False
        assert args.outdir == "../results"
        assert args.fee == 10.0

    def test_grid_bounds_default_to_refdata_not_the_parser(self):
        """No window or signal range lives in the CLI; the indicator row owns them."""
        args = parse_args(REQUIRED)
        assert (args.win_min, args.win_max, args.win_step) == (None, None, None)
        assert (args.sig_min, args.sig_max, args.sig_step) == (None, None, None)

    @pytest.mark.parametrize("flag", ["--indicator", "--strategy", "--asset"])
    def test_catalog_names_are_required(self, flag):
        at = REQUIRED.index(flag)
        argv = REQUIRED[:at] + REQUIRED[at + 2:]
        with pytest.raises(SystemExit):
            parse_args(argv)

    def test_the_parser_holds_no_catalog(self):
        """Any name parses; REFDATA decides in ``main``."""
        args = parse_args(["--indicator", "macd", "--strategy", "random", "--asset", "forex"])
        assert (args.indicator, args.strategy, args.asset) == ("macd", "random", "forex")
        for name in ("INDICATORS", "STRATEGIES", "ASSET_TRADING_PERIODS"):
            assert not hasattr(cli, name)

    def test_custom_symbol(self):
        assert parse_args([*REQUIRED, "--symbol", "AAPL"]).symbol == "AAPL"

    def test_no_grid_flag(self):
        assert parse_args([*REQUIRED, "--no-grid"]).no_grid is True

    def test_custom_grid_bounds(self):
        args = parse_args([
            *REQUIRED,
            "--win-min", "10", "--win-max", "50", "--win-step", "10",
            "--sig-min", "0.5", "--sig-max", "2.0", "--sig-step", "0.5",
        ])
        assert (args.win_min, args.win_max, args.win_step) == (10, 50, 10)
        assert args.sig_min == pytest.approx(0.5)
        assert args.sig_max == pytest.approx(2.0)
        assert args.sig_step == pytest.approx(0.5)

    def test_custom_fee(self):
        assert parse_args([*REQUIRED, "--fee", "5.5"]).fee == pytest.approx(5.5)

    def test_verbose_flag(self):
        assert parse_args([*REQUIRED, "-v"]).verbose is True

    def test_custom_dates(self):
        args = parse_args([*REQUIRED, "--start", "2020-01-01", "--end", "2025-01-01"])
        assert (args.start, args.end) == ("2020-01-01", "2025-01-01")


class TestGridAxes:
    def test_refdata_columns_are_the_default(self, refdata_stub):
        args = parse_args(REQUIRED)
        windows, signals = _grid_axes(args, "get_bollinger_band", refdata_stub)
        assert windows == tuple(range(10, 101, 5))
        assert signals[0] == pytest.approx(0.25)
        assert signals[-1] == pytest.approx(2.50)

    def test_an_explicit_flag_wins(self, refdata_stub):
        args = parse_args([*REQUIRED, "--win-min", "20", "--win-max", "30", "--win-step", "10"])
        windows, _ = _grid_axes(args, "get_bollinger_band", refdata_stub)
        assert windows == (20, 30)

    def test_a_null_refdata_bound_must_be_passed(self, refdata_stub):
        """RSI seeds no SIG_MIN; the CLI says so instead of inventing one."""
        args = parse_args(["--indicator", "rsi", "--strategy", "momentum", "--asset", "crypto"])
        with pytest.raises(SystemExit, match="--sig-min"):
            _grid_axes(args, "get_rsi", refdata_stub)


def _price_frame(n: int = 120) -> pd.DataFrame:
    return pd.DataFrame({
        "t": pd.date_range("2021-01-01", periods=n, freq="D").strftime("%Y-%m-%d"),
        "v": [100 + i * 0.5 for i in range(n)],
    })


class TestMainResolvesThroughRefdata:
    def _run(self, argv, refdata, tmp_path):
        with patch("quant.cli.YahooFinance") as yf_cls, \
             patch("quant.cli.Performance") as perf_cls:
            yf_cls.return_value.get_historical_price.return_value = _price_frame()
            perf_cls.return_value.data = pd.DataFrame({"x": [1]})
            main(parse_args([*argv, "--no-grid", "--outdir", str(tmp_path)]), refdata=refdata)
            return perf_cls.call_args

    def test_names_resolve_to_catalog_values(self, refdata_stub, tmp_path):
        call = self._run(
            ["--indicator", "sma", "--strategy", "reversion", "--asset", "equity"],
            refdata_stub, tmp_path,
        )
        config = call.args[1]
        assert config.indicator_name == "get_sma"
        assert config.signal_func is SignalDirection.reversion_band_signal
        assert config.trading_period == 252

    def test_a_bounded_indicator_picks_the_bounded_signal(self, refdata_stub, tmp_path):
        call = self._run(
            ["--indicator", "rsi", "--strategy", "momentum", "--asset", "crypto"],
            refdata_stub, tmp_path,
        )
        assert call.args[1].signal_func is SignalDirection.momentum_bounded_signal

    @pytest.mark.parametrize("argv, table", [
        (["--indicator", "macd", "--strategy", "momentum", "--asset", "crypto"], "INDICATOR"),
        (["--indicator", "sma", "--strategy", "random", "--asset", "crypto"], "SIGNAL_TYPE"),
        (["--indicator", "sma", "--strategy", "momentum", "--asset", "forex"], "ASSET_TYPE"),
    ])
    def test_a_name_refdata_lacks_is_refused_by_name(self, argv, table, refdata_stub, tmp_path):
        with pytest.raises(SystemExit, match=f"REFDATA.{table}"):
            self._run(argv, refdata_stub, tmp_path)

    def test_the_default_reader_is_the_redis_snapshot(self, tmp_path):
        reader = MagicMock()
        reader.get.side_effect = AssertionError("stop here")
        with patch("quant.cli.RedisRefData", return_value=reader) as redis_cls, \
             patch("quant.cli.get_redis_url", return_value="redis://unit"), \
             pytest.raises(AssertionError, match="stop here"):
            main(parse_args([*REQUIRED, "--outdir", str(tmp_path)]))
        redis_cls.assert_called_once_with("redis://unit")
