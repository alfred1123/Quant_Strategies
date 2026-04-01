"""
Streamlit UI for the backtest pipeline.

Launch:
    cd scripts/bt && streamlit run app.py
"""

import logging
import sys
import os

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# Ensure backtest modules are importable
sys.path.insert(0, os.path.dirname(__file__))

from data import YahooFinance, AlphaVantage
from ta import TechnicalAnalysis
from strat import Strategy
from perf import Performance
from log_config import setup_logging
from param_opt import ParametersOptimization

setup_logging()
logger = logging.getLogger(__name__)

# ── Registry of available indicators and strategies ─────────────────

INDICATORS = {
    "Bollinger Band (z-score)": "get_bollinger_band",
    "SMA": "get_sma",
    "EMA": "get_ema",
    "RSI": "get_rsi",
}

STRATEGIES = {
    "Momentum": Strategy.momentum_const_signal,
    "Reversion": Strategy.reversion_const_signal,
}

ASSET_TYPES = {
    "Crypto (365 days/year)": 365,
    "Equity (252 trading days/year)": 252,
}

# ── Page config ─────────────────────────────────────────────────────

st.set_page_config(page_title="Quant Strategies — Backtest", layout="wide")
st.title("Quant Strategies — Backtest Dashboard")

# ── Sidebar inputs ──────────────────────────────────────────────────

with st.sidebar:
    st.header("Configuration")

    symbol = st.text_input("Symbol", value="BTC-USD",
                           help="Yahoo Finance ticker: AAPL, BTC-USD, ^GSPC, SPY")

    col_start, col_end = st.columns(2)
    with col_start:
        start_date = st.date_input("Start date",
                                   value=pd.Timestamp("2016-01-01"))
    with col_end:
        end_date = st.date_input("End date",
                                 value=pd.Timestamp("2026-04-01"))

    asset_type = st.selectbox("Asset type", list(ASSET_TYPES.keys()))
    trading_period = ASSET_TYPES[asset_type]

    indicator_name = st.selectbox("Indicator", list(INDICATORS.keys()))
    strategy_name = st.selectbox("Strategy", list(STRATEGIES.keys()))

    st.divider()
    st.subheader("Single Backtest")
    window = st.number_input("Window", min_value=2, max_value=500, value=20)
    signal = st.number_input("Signal threshold", min_value=0.0,
                             max_value=10.0, value=1.0, step=0.25)

    st.divider()
    st.subheader("Grid Search")
    col_w, col_s = st.columns(2)
    with col_w:
        win_min = st.number_input("Window min", value=5, min_value=2)
        win_max = st.number_input("Window max", value=100, min_value=2)
        win_step = st.number_input("Window step", value=5, min_value=1)
    with col_s:
        sig_min = st.number_input("Signal min", value=0.25, step=0.25)
        sig_max = st.number_input("Signal max", value=2.50, step=0.25)
        sig_step = st.number_input("Signal step", value=0.25, step=0.05,
                                   min_value=0.05)

    st.divider()
    st.subheader("Costs")
    st.number_input("Transaction fee (bps)", value=5.0, disabled=True,
                    help="Fixed at 5 bps (0.05%) per unit of turnover. "
                         "Coming soon: configurable fees.")
    st.caption("🔒 Fee (Coming Soon)")


# ── Helper: fetch data (cached across reruns) ───────────────────────

@st.cache_data(show_spinner="Fetching price data...")
def fetch_data(symbol, start, end):
    yf = YahooFinance()
    price = yf.get_historical_price(symbol, str(start), str(end))
    yf.get_historical_price.cache_clear()  # don't keep lru_cache across runs
    return pd.DataFrame({
        "datetime": price["t"],
        "price": price["v"],
        "factor": price["v"],
    })


# ── Fetch data ──────────────────────────────────────────────────────

try:
    df = fetch_data(symbol, start_date, end_date)
except Exception as exc:
    logger.error("Failed to fetch data for %s: %s", symbol, exc)
    st.error(f"Failed to fetch data: {exc}")
    st.stop()

st.sidebar.success(f"Loaded {len(df)} daily bars")

# ── Tab layout ──────────────────────────────────────────────────────

tab_single, tab_grid = st.tabs(["Single Backtest", "Parameter Optimization"])

# ── Tab 1: Single backtest ──────────────────────────────────────────

with tab_single:
    run_single = st.button("Run Backtest", type="primary", key="run_single")

    if run_single:
        data_copy = df.copy()
        ta = TechnicalAnalysis(data_copy)
        indicator_func = getattr(ta, INDICATORS[indicator_name])
        strategy_func = STRATEGIES[strategy_name]

        perf = Performance(data_copy, trading_period, indicator_func,
                           strategy_func, window, signal)

        # Performance metrics side-by-side
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Strategy Performance")
            st.dataframe(perf.get_strategy_performance().to_frame("Value"),
                         use_container_width=True)
        with col2:
            st.subheader("Buy & Hold Performance")
            st.dataframe(perf.get_buy_hold_performance().to_frame("Value"),
                         use_container_width=True)

        # Cumulative return chart
        chart_df = perf.data.dropna(subset=["cumu"]).copy()
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=chart_df["datetime"], y=chart_df["cumu"],
                                 mode="lines", name="Strategy"))
        fig.add_trace(go.Scatter(x=chart_df["datetime"],
                                 y=chart_df["buy_hold_cumu"],
                                 mode="lines", name="Buy & Hold"))
        fig.update_layout(title=f"{symbol} — Cumulative Return",
                          xaxis_title="Date", yaxis_title="Cumulative Return",
                          height=500)
        st.plotly_chart(fig, use_container_width=True)

        # Drawdown chart
        fig_dd = go.Figure()
        fig_dd.add_trace(go.Scatter(x=chart_df["datetime"], y=-chart_df["dd"],
                                    fill="tozeroy", name="Strategy DD"))
        fig_dd.add_trace(go.Scatter(x=chart_df["datetime"],
                                    y=-chart_df["buy_hold_dd"],
                                    fill="tozeroy", name="Buy & Hold DD"))
        fig_dd.update_layout(title="Drawdown", xaxis_title="Date",
                             yaxis_title="Drawdown", height=350)
        st.plotly_chart(fig_dd, use_container_width=True)

        # Download daily PnL
        csv = perf.data.to_csv(index=False)
        st.download_button("Download daily PnL (CSV)", csv,
                           file_name=f"perf_{symbol}.csv", mime="text/csv")

# ── Tab 2: Parameter optimization ──────────────────────────────────

with tab_grid:
    run_grid = st.button("Run Grid Search", type="primary", key="run_grid")

    if run_grid:
        window_list = list(range(int(win_min), int(win_max) + 1, int(win_step)))
        signal_list = list(np.arange(sig_min, sig_max + sig_step / 2, sig_step))
        total = len(window_list) * len(signal_list)

        if total > 5000:
            st.warning(f"Grid has {total} combinations — this may take a while.")

        data_copy = df.copy()
        ta = TechnicalAnalysis(data_copy)
        indicator_func = getattr(ta, INDICATORS[indicator_name])
        strategy_func = STRATEGIES[strategy_name]

        opt = ParametersOptimization(
            ta.data, trading_period, indicator_func, strategy_func,
        )

        # Run with progress bar
        progress = st.progress(0, text="Running grid search...")
        results = []
        for i, row in enumerate(
            opt.optimize(tuple(window_list), tuple(signal_list))
        ):
            results.append(row)
            progress.progress((i + 1) / total,
                              text=f"Evaluated {i + 1}/{total} combinations")

        progress.empty()
        param_perf = pd.DataFrame(results, columns=["window", "signal", "sharpe"])

        # Best parameters
        best = param_perf.loc[param_perf["sharpe"].idxmax()]
        st.success(
            f"**Best:** window={int(best['window'])}, "
            f"signal={best['signal']:.2f}, Sharpe={best['sharpe']:.4f}"
        )

        # Top 10 table
        st.subheader("Top 10 Parameter Combinations")
        st.dataframe(
            param_perf.sort_values("sharpe", ascending=False).head(10)
            .reset_index(drop=True),
            use_container_width=True,
        )

        # Heatmap
        st.subheader("Sharpe Ratio Heatmap")
        pivot = param_perf.pivot(index="window", columns="signal",
                                values="sharpe")
        fig_hm = go.Figure(data=go.Heatmap(
            z=pivot.values,
            x=[f"{s:.2f}" for s in pivot.columns],
            y=pivot.index.tolist(),
            colorscale="RdYlGn",
            zmid=0,
            text=np.round(pivot.values, 2),
            texttemplate="%{text}",
            hovertemplate="Window: %{y}<br>Signal: %{x}<br>Sharpe: %{z:.4f}",
        ))
        fig_hm.update_layout(
            title=f"{symbol} {indicator_name} + {strategy_name} — Sharpe Heatmap",
            xaxis_title="Signal Threshold",
            yaxis_title="Indicator Window",
            height=max(400, len(window_list) * 30),
        )
        st.plotly_chart(fig_hm, use_container_width=True)

        # Download grid results
        csv = param_perf.to_csv(index=False)
        st.download_button("Download grid results (CSV)", csv,
                           file_name=f"opt_{symbol}.csv", mime="text/csv")
