"""Unit tests for the Streamlit backtest UI (src/app.py).

Uses ``streamlit.testing.v1.AppTest`` to render the app headlessly without a
browser.  All network calls (yfinance) are mocked so the tests are
self-contained and fast.

Launch the live UI manually with::

    cd src && streamlit run app.py
"""

import numpy as np
import pandas as pd
import pytest
from unittest.mock import MagicMock, patch

from streamlit.testing.v1 import AppTest

APP_PATH = "src/app.py"
_N_BARS = 200  # synthetic daily bars


# ── Helpers ──────────────────────────────────────────────────────────


def _make_ticker_mock(n: int = _N_BARS) -> MagicMock:
    """Return a MagicMock that replaces the ``yfinance.Ticker`` *callable*.

    When used with ``patch("yfinance.Ticker", _make_ticker_mock())``, calling
    ``yfinance.Ticker(symbol)`` returns a mock Ticker instance whose
    ``.history()`` method yields ``n`` daily bars of synthetic close prices.

    Mock structure mirrors the real ``yfinance.Ticker.history()`` output:
    a DataFrame with a DatetimeIndex and columns ``Close`` and ``Volume``.
    See: https://github.com/ranaroussi/yfinance (Ticker.history docs)
    """
    rng = np.random.default_rng(42)
    dates = pd.date_range("2020-01-01", periods=n, freq="D")
    close = 100.0 + np.cumsum(rng.standard_normal(n) * 0.5)
    volume = np.full(n, 1_000_000.0)
    hist = pd.DataFrame({"Close": close, "Volume": volume}, index=dates)

    mock_ticker = MagicMock()
    mock_ticker.history.return_value = hist
    return MagicMock(return_value=mock_ticker)  # mock for yfinance.Ticker(symbol)


def _run_app(ticker_mock: MagicMock | None = None) -> AppTest:
    """Instantiate and run AppTest with an optionally injected ``yfinance.Ticker`` mock.

    ``yfinance`` is lazy-imported inside ``YahooFinance.get_historical_price``
    so we patch at the ``yfinance.Ticker`` callable level before the app runs.
    The mock produced by ``_make_ticker_mock()`` is a callable whose return
    value acts as the Ticker instance (i.e., it replaces the Ticker constructor).
    """
    if ticker_mock is None:
        ticker_mock = _make_ticker_mock()
    with patch("yfinance.Ticker", ticker_mock):
        at = AppTest.from_file(APP_PATH, default_timeout=30)
        at.run()
    return at


# ── Tests: app load ───────────────────────────────────────────────────


class TestAppLoads:
    def test_app_loads_without_exception(self):
        """App initialises and renders without raising an unhandled exception."""
        at = _run_app()
        assert not at.exception

    def test_app_title_present(self):
        """Dashboard title contains 'Quant Strategies'."""
        at = _run_app()
        assert not at.exception
        title_values = [t.value for t in at.title]
        assert any("Quant Strategies" in v for v in title_values)

    def test_sidebar_shows_loaded_bars(self):
        """Sidebar displays a success message confirming data was loaded."""
        at = _run_app()
        assert not at.exception
        success_texts = [s.value for s in at.success]
        assert any("daily bars" in str(t) for t in success_texts)

    def test_five_tabs_rendered(self):
        """All five navigation tabs are present in the layout."""
        at = _run_app()
        assert not at.exception
        tab_labels = {t.label for t in at.tabs}
        expected = {
            "Full Analysis",
            "Single Backtest",
            "Parameter Optimization",
            "Walk-Forward Test",
            "Trading",
        }
        assert expected.issubset(tab_labels)


# ── Tests: sidebar defaults ───────────────────────────────────────────


class TestSidebarDefaults:
    def test_default_symbol_is_btc(self):
        """Default symbol text input is 'BTC-USD'."""
        at = _run_app()
        assert not at.exception
        symbols = [t.value for t in at.text_input]
        assert "BTC-USD" in symbols

    def test_default_window_is_20(self):
        """Default window number input value is 20."""
        at = _run_app()
        assert not at.exception
        inputs = {ni.label: ni.value for ni in at.number_input}
        assert inputs.get("Window") == 20

    def test_default_signal_is_1(self):
        """Default signal threshold is 1.0."""
        at = _run_app()
        assert not at.exception
        inputs = {ni.label: ni.value for ni in at.number_input}
        assert inputs.get("Signal threshold") == pytest.approx(1.0)

    def test_default_fee_bps_is_5(self):
        """Default transaction fee is 5 bps."""
        at = _run_app()
        assert not at.exception
        inputs = {ni.label: ni.value for ni in at.number_input}
        assert inputs.get("Transaction fee (bps)") == pytest.approx(5.0)


# ── Tests: data error handling ────────────────────────────────────────


class TestDataFetchErrorHandling:
    def test_app_shows_error_on_data_failure(self):
        """App renders a st.error (not an exception) when data fetch fails.

        ``@st.cache_data`` on ``fetch_data`` persists across AppTest instances
        within the same pytest session.  Clear the global cache first so the
        failing mock is actually invoked and not short-circuited by a cached
        successful result from a previous test.
        """
        import streamlit as st

        # Clear all st.cache_data so fetch_data is re-executed, not cached
        st.cache_data.clear()

        failing_ticker = MagicMock(side_effect=RuntimeError("network error"))
        with patch("yfinance.Ticker", failing_ticker):
            at = AppTest.from_file(APP_PATH, default_timeout=30)
            at.run()

        # st.stop() is called after st.error — the app halts gracefully
        assert not at.exception
        assert len(at.error) > 0
