import numpy as np
import pandas as pd
import pytest

from strat import TechnicalAnalysis


class TestSMA:
    def test_sma_known_values(self, simple_factor_df):
        ta = TechnicalAnalysis(simple_factor_df)
        sma = ta.get_sma(3)
        # SMA(3) of [1,2,3,4,5,...] → [NaN, NaN, 2, 3, 4, ...]
        assert np.isnan(sma.iloc[0])
        assert np.isnan(sma.iloc[1])
        assert sma.iloc[2] == pytest.approx(2.0)
        assert sma.iloc[3] == pytest.approx(3.0)
        assert sma.iloc[4] == pytest.approx(4.0)

    def test_sma_window_1_equals_factor(self, simple_factor_df):
        ta = TechnicalAnalysis(simple_factor_df)
        sma = ta.get_sma(1)
        pd.testing.assert_series_equal(sma, simple_factor_df["factor"], check_names=False)

    def test_sma_length_matches_input(self, sample_ohlc_df):
        ta = TechnicalAnalysis(sample_ohlc_df)
        sma = ta.get_sma(10)
        assert len(sma) == len(sample_ohlc_df)

    def test_sma_leading_nans(self, simple_factor_df):
        ta = TechnicalAnalysis(simple_factor_df)
        sma = ta.get_sma(5)
        assert sma.iloc[:4].isna().all()
        assert not np.isnan(sma.iloc[4])


class TestEMA:
    def test_ema_no_nans(self, simple_factor_df):
        ta = TechnicalAnalysis(simple_factor_df)
        ema = ta.get_ema(3)
        # EMA should not produce NaNs (ewm handles warmup)
        assert not ema.isna().any()

    def test_ema_length_matches_input(self, sample_ohlc_df):
        ta = TechnicalAnalysis(sample_ohlc_df)
        ema = ta.get_ema(10)
        assert len(ema) == len(sample_ohlc_df)

    def test_ema_first_value_equals_first_factor(self, simple_factor_df):
        ta = TechnicalAnalysis(simple_factor_df)
        ema = ta.get_ema(5)
        # With adjust=False, EMA starts at the first value
        assert ema.iloc[0] == pytest.approx(simple_factor_df["factor"].iloc[0])

    def test_ema_responds_to_trend(self, simple_factor_df):
        ta = TechnicalAnalysis(simple_factor_df)
        ema = ta.get_ema(3)
        # For an increasing series, EMA should be increasing
        diffs = ema.diff().dropna()
        assert (diffs > 0).all()


class TestRSI:
    def test_rsi_bounded_0_100(self, sample_ohlc_df):
        ta = TechnicalAnalysis(sample_ohlc_df)
        rsi = ta.get_rsi(14)
        valid = rsi.dropna()
        assert (valid >= 0).all()
        assert (valid <= 100).all()

    def test_rsi_all_up(self):
        df = pd.DataFrame({"factor": np.arange(1, 51, dtype=float)})
        ta = TechnicalAnalysis(df)
        rsi = ta.get_rsi(14)
        valid = rsi.dropna()
        # All positive changes → RSI near 100
        assert valid.iloc[-1] == pytest.approx(100.0)

    def test_rsi_all_down(self):
        df = pd.DataFrame({"factor": np.arange(50, 0, -1, dtype=float)})
        ta = TechnicalAnalysis(df)
        rsi = ta.get_rsi(14)
        valid = rsi.dropna()
        # All negative changes → RSI near 0
        assert valid.iloc[-1] == pytest.approx(0.0)

    def test_rsi_shorter_due_to_diff(self, simple_factor_df):
        ta = TechnicalAnalysis(simple_factor_df)
        rsi = ta.get_rsi(3)
        # RSI uses diff(1) which drops first row, then rolling(3) adds more NaNs
        # Result should be shorter than input due to dropna in implementation
        assert len(rsi) == len(simple_factor_df) - 1


class TestBollingerBand:
    def test_bollinger_z_mean_near_zero(self, sample_ohlc_df):
        ta = TechnicalAnalysis(sample_ohlc_df)
        z = ta.get_bollinger_band(20)
        valid = z.dropna()
        # Z-score should have mean near zero over many observations
        assert abs(valid.mean()) < 1.0

    def test_bollinger_z_length(self, sample_ohlc_df):
        ta = TechnicalAnalysis(sample_ohlc_df)
        z = ta.get_bollinger_band(10)
        assert len(z) == len(sample_ohlc_df)

    def test_bollinger_z_leading_nans(self, simple_factor_df):
        ta = TechnicalAnalysis(simple_factor_df)
        z = ta.get_bollinger_band(5)
        assert z.iloc[:4].isna().all()

    def test_bollinger_z_constant_series_is_nan(self):
        df = pd.DataFrame({"factor": [5.0] * 20})
        ta = TechnicalAnalysis(df)
        z = ta.get_bollinger_band(5)
        # Constant series → std=0 → z=NaN (division by zero)
        valid_region = z.iloc[4:]
        assert valid_region.isna().all()


class TestStochasticOscillator:
    def test_stochastic_bounded_0_100(self, sample_ohlc_df):
        ta = TechnicalAnalysis(sample_ohlc_df)
        d = ta.get_stochastic_oscillator(14)
        valid = d.dropna()
        assert (valid >= 0).all()
        assert (valid <= 100).all()

    def test_stochastic_length(self, sample_ohlc_df):
        ta = TechnicalAnalysis(sample_ohlc_df)
        d = ta.get_stochastic_oscillator(10)
        assert len(d) == len(sample_ohlc_df)

    def test_stochastic_leading_nans(self, sample_ohlc_df):
        ta = TechnicalAnalysis(sample_ohlc_df)
        d = ta.get_stochastic_oscillator(14)
        # Rolling window of 14 for both K and D
        assert d.iloc[:13].isna().all()
