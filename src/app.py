"""Streamlit UI for the backtest pipeline.

Launch:
    cd src && streamlit run app.py
"""

import logging
import os

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from data import YahooFinance, AlphaVantage
from strat import Strategy, StrategyConfig
from perf import Performance
from log_config import setup_logging
from param_opt import ParametersOptimization
from walk_forward import WalkForward

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

st.markdown("""
<style>
/* Primary buttons — larger, bolder, with hover effect */
button[kind="primary"] {
    font-size: 1.1rem !important;
    font-weight: 700 !important;
    padding: 0.6rem 2.4rem !important;
    border-radius: 0.5rem !important;
    transition: transform 0.1s, box-shadow 0.1s !important;
    box-shadow: 0 2px 6px rgba(0,0,0,0.15) !important;
}
button[kind="primary"]:hover {
    transform: translateY(-1px) !important;
    box-shadow: 0 4px 12px rgba(0,0,0,0.25) !important;
}
button[kind="primary"]:active {
    transform: translateY(0px) !important;
}
</style>
""", unsafe_allow_html=True)

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
    fee_bps = st.number_input("Transaction fee (bps)", value=5.0,
                              min_value=0.0, max_value=100.0, step=0.5,
                              help="Fee in basis points per unit of turnover "
                                   "(1 bp = 0.01%).")

    st.divider()
    st.subheader("Walk-Forward Test")
    split_ratio = st.slider("Train/test split ratio", min_value=0.2,
                            max_value=0.8, value=0.5, step=0.05,
                            help="Fraction of data used for in-sample training.")


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


# ── Helpers: build grid lists & config (shared by all tabs) ─────────

def _build_grid_lists():
    """Return (window_list, signal_list) from sidebar inputs."""
    wl = list(range(int(win_min), int(win_max) + 1, int(win_step)))
    sl = list(np.arange(sig_min, sig_max + sig_step / 2, sig_step))
    return wl, sl


def _build_config():
    return StrategyConfig(
        indicator_name=INDICATORS[indicator_name],
        strategy_func=STRATEGIES[strategy_name],
        trading_period=trading_period,
    )


# ── Fetch data ──────────────────────────────────────────────────────

try:
    df = fetch_data(symbol, start_date, end_date)
except Exception as exc:
    logger.error("Failed to fetch data for %s: %s", symbol, exc)
    st.error(f"Failed to fetch data: {exc}")
    st.stop()

st.sidebar.success(f"Loaded {len(df)} daily bars")

# ── Tab layout ──────────────────────────────────────────────────────

tab_full, tab_single, tab_grid, tab_wf = st.tabs(
    ["Full Analysis", "Single Backtest", "Parameter Optimization", "Walk-Forward Test"]
)

# ── Tab 0: Full Analysis ───────────────────────────────────────────

with tab_full:
    run_full = st.button("Run Full Analysis", type="primary", key="run_full")

    if run_full:
        config = _build_config()

        # ── Step 1: Grid Search ─────────────────────────────────────
        window_list, signal_list = _build_grid_lists()
        total = len(window_list) * len(signal_list)

        if total == 0:
            st.error("Grid is empty — check Window/Signal ranges in the sidebar.")
            st.stop()

        if total > 5000:
            st.warning(f"Grid has {total} combinations — this may take a while.")

        opt = ParametersOptimization(df.copy(), config, fee_bps=fee_bps)

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

        # ── Walk-Forward ────────────────────────────────────────────
        wf_result = None
        wf_split_idx = None
        try:
            wf = WalkForward(df.copy(), split_ratio, config, fee_bps=fee_bps)
            wf_result = wf.run(tuple(window_list), tuple(signal_list))
            wf_split_idx = wf.split_idx
        except ValueError as exc:
            st.warning(f"Walk-forward skipped: {exc}")

        # Persist to session_state so heatmap clicks survive reruns
        st.session_state["full_param_perf"] = param_perf
        st.session_state["full_config"] = config
        st.session_state["full_fee_bps"] = fee_bps
        st.session_state["full_symbol"] = symbol
        st.session_state["full_indicator"] = indicator_name
        st.session_state["full_strategy"] = strategy_name
        st.session_state["full_wf_result"] = wf_result
        st.session_state["full_wf_split_idx"] = wf_split_idx
        st.session_state["full_df"] = df.copy()

    # ── Render results from session_state ───────────────────────────
    if "full_param_perf" in st.session_state:
        param_perf = st.session_state["full_param_perf"]
        config = st.session_state["full_config"]
        _fee_bps = st.session_state["full_fee_bps"]
        _symbol = st.session_state["full_symbol"]
        _indicator = st.session_state["full_indicator"]
        _strategy = st.session_state["full_strategy"]
        wf_result = st.session_state["full_wf_result"]
        wf_split_idx = st.session_state["full_wf_split_idx"]
        _df = st.session_state["full_df"]

        valid = param_perf["sharpe"].dropna()
        if valid.empty:
            st.error("All Sharpe ratios are NaN — check data length vs window sizes.")
            st.stop()
        best = param_perf.loc[valid.idxmax()]
        best_window = int(best["window"])
        best_signal = float(best["signal"])

        # ── Heatmap with click support ──────────────────────────────
        st.header("1. Parameter Optimization")
        st.success(
            f"**Optimal parameters:** window={best_window}, "
            f"signal={best_signal:.2f}, Sharpe={best['sharpe']:.4f}"
        )

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
            title=f"{_symbol} {_indicator} + {_strategy} — Sharpe Heatmap (click a cell)",
            xaxis_title="Signal Threshold",
            yaxis_title="Indicator Window",
            height=max(400, len(pivot.index) * 30),
        )

        hm_selection = st.plotly_chart(fig_hm, use_container_width=True)

        # Determine which params to show
        windows = sorted(param_perf["window"].unique().astype(int))
        signals = sorted(param_perf["signal"].unique())

        st.subheader("Select parameters")
        col_pw, col_ps = st.columns(2)
        with col_pw:
            sel_window = st.selectbox(
                "Window", windows,
                index=windows.index(best_window),
                key="full_sel_window",
            )
        with col_ps:
            sig_labels = [f"{s:.2f}" for s in signals]
            sel_signal_label = st.selectbox(
                "Signal", sig_labels,
                index=sig_labels.index(f"{best_signal:.2f}"),
                key="full_sel_signal",
            )
            sel_signal = float(sel_signal_label)

        # Show Sharpe for the selected combo
        match = param_perf[
            (param_perf["window"] == sel_window)
            & (np.isclose(param_perf["signal"], sel_signal))
        ]
        if not match.empty:
            sel_sharpe = match.iloc[0]["sharpe"]
            st.info(f"**Selected:** window={sel_window}, signal={sel_signal:.2f}, Sharpe={sel_sharpe:.4f}")

        st.divider()

        # ── Performance for selected params ─────────────────────────
        st.header(f"2. Strategy Performance (window={sel_window}, signal={sel_signal:.2f})")

        perf = Performance(_df.copy(), config, sel_window, sel_signal,
                           fee_bps=_fee_bps)

        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Strategy")
            st.dataframe(perf.get_strategy_performance().to_frame("Value"),
                         use_container_width=True)
        with col2:
            st.subheader("Buy & Hold")
            st.dataframe(perf.get_buy_hold_performance().to_frame("Value"),
                         use_container_width=True)

        # Cumulative return chart
        chart_df = perf.data.dropna(subset=["cumu"]).copy()
        fig_ret = go.Figure()
        fig_ret.add_trace(go.Scatter(
            x=chart_df["datetime"], y=chart_df["cumu"],
            mode="lines", name="Strategy",
        ))
        fig_ret.add_trace(go.Scatter(
            x=chart_df["datetime"], y=chart_df["buy_hold_cumu"],
            mode="lines", name="Buy & Hold",
        ))
        fig_ret.update_layout(
            title=f"{_symbol} — Cumulative Return (window={sel_window}, signal={sel_signal:.2f})",
            xaxis_title="Date", yaxis_title="Cumulative Return",
            height=500,
        )
        st.plotly_chart(fig_ret, use_container_width=True)

        # Drawdown chart
        fig_dd = go.Figure()
        fig_dd.add_trace(go.Scatter(
            x=chart_df["datetime"], y=-chart_df["dd"],
            fill="tozeroy", name="Strategy DD",
        ))
        fig_dd.add_trace(go.Scatter(
            x=chart_df["datetime"], y=-chart_df["buy_hold_dd"],
            fill="tozeroy", name="Buy & Hold DD",
        ))
        fig_dd.update_layout(title="Drawdown", xaxis_title="Date",
                             yaxis_title="Drawdown", height=350)
        st.plotly_chart(fig_dd, use_container_width=True)

        st.divider()

        # ── Walk-Forward Results ────────────────────────────────────
        st.header("3. Overfitting Analysis")
        if wf_result is not None:
            st.info(
                f"**Walk-forward best (in-sample):** window={wf_result.best_window}, "
                f"signal={wf_result.best_signal:.2f}"
            )

            ov = wf_result.overfitting_ratio
            if np.isnan(ov):
                st.warning("Overfitting ratio: N/A (in-sample Sharpe is zero or NaN)")
            elif ov < 0.3:
                st.success(f"Overfitting ratio: **{ov:.4f}** — Low risk of overfitting")
            elif ov < 0.5:
                st.warning(f"Overfitting ratio: **{ov:.4f}** — Moderate overfitting risk")
            else:
                st.error(f"Overfitting ratio: **{ov:.4f}** — High overfitting risk")

            summary = wf_result.summary()
            st.dataframe(summary, use_container_width=True)

            # Walk-forward cumulative return chart
            wf_perf = Performance(
                _df.copy(), config, wf_result.best_window, wf_result.best_signal,
                fee_bps=_fee_bps,
            )
            wf_chart = wf_perf.data.dropna(subset=["cumu"]).copy()

            fig_wf = go.Figure()
            fig_wf.add_trace(go.Scatter(
                x=wf_chart["datetime"], y=wf_chart["cumu"],
                mode="lines", name="Strategy",
            ))
            fig_wf.add_trace(go.Scatter(
                x=wf_chart["datetime"], y=wf_chart["buy_hold_cumu"],
                mode="lines", name="Buy & Hold",
            ))
            if ("datetime" in wf_chart.columns
                    and wf_split_idx is not None
                    and wf_split_idx < len(wf_chart)):
                split_date = str(wf_chart["datetime"].iloc[wf_split_idx])
                fig_wf.add_vline(
                    x=split_date, line_dash="dash", line_color="red",
                )
                fig_wf.add_annotation(
                    x=split_date, y=1, yref="paper",
                    text="Train/Test Split", showarrow=False,
                    xanchor="left", yanchor="top",
                    font=dict(color="red"),
                )
            fig_wf.update_layout(
                title=f"{_symbol} — Walk-Forward Cumulative Return",
                xaxis_title="Date", yaxis_title="Cumulative Return",
                height=500,
            )
            st.plotly_chart(fig_wf, use_container_width=True)
        else:
            st.warning("Walk-forward test was skipped (see above).")

        # Download all results
        st.divider()
        col_dl1, col_dl2 = st.columns(2)
        with col_dl1:
            st.download_button("Grid results (CSV)",
                               param_perf.to_csv(index=False),
                               file_name=f"opt_{_symbol}.csv", mime="text/csv",
                               key="full_dl_grid")
        with col_dl2:
            st.download_button("Daily PnL (CSV)",
                               perf.data.to_csv(index=False),
                               file_name=f"perf_{_symbol}.csv", mime="text/csv",
                               key="full_dl_perf")
        if wf_result is not None:
            st.download_button("Walk-forward (CSV)",
                               wf_result.summary().to_csv(),
                               file_name=f"wf_{_symbol}.csv", mime="text/csv",
                               key="full_dl_wf")

# ── Tab 1: Single backtest ──────────────────────────────────────────

with tab_single:
    run_single = st.button("Run Backtest", type="primary", key="run_single")

    if run_single:
        data_copy = df.copy()
        config = _build_config()

        perf = Performance(data_copy, config, window, signal,
                           fee_bps=fee_bps)

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
        window_list, signal_list = _build_grid_lists()
        total = len(window_list) * len(signal_list)

        if total == 0:
            st.error("Grid is empty — check Window/Signal ranges in the sidebar.")
            st.stop()

        if total > 5000:
            st.warning(f"Grid has {total} combinations — this may take a while.")

        data_copy = df.copy()
        config = _build_config()

        opt = ParametersOptimization(
            data_copy, config, fee_bps=fee_bps,
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
        valid = param_perf["sharpe"].dropna()
        if valid.empty:
            st.error("All Sharpe ratios are NaN — check data length vs window sizes.")
            st.stop()
        best = param_perf.loc[valid.idxmax()]
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

# ── Tab 3: Walk-forward overfitting test ───────────────────────────

with tab_wf:
    run_wf = st.button("Run Walk-Forward Test", type="primary", key="run_wf")

    if run_wf:
        window_list, signal_list = _build_grid_lists()

        if not window_list or not signal_list:
            st.error("Grid is empty — check Window/Signal ranges in the sidebar.")
            st.stop()

        data_copy = df.copy()
        config = _build_config()

        try:
            wf = WalkForward(
                data_copy, split_ratio, config, fee_bps=fee_bps,
            )
        except ValueError as exc:
            st.error(f"Walk-forward setup failed: {exc}")
            st.stop()

        with st.spinner("Running walk-forward test (grid search on in-sample)..."):
            result = wf.run(tuple(window_list), tuple(signal_list))

        st.success(
            f"**Best params (in-sample):** window={result.best_window}, "
            f"signal={result.best_signal:.2f}"
        )

        # Overfitting ratio with colour coding
        ov = result.overfitting_ratio
        if np.isnan(ov):
            st.warning("Overfitting ratio: N/A (in-sample Sharpe is zero or NaN)")
        elif ov < 0.3:
            st.success(f"Overfitting ratio: **{ov:.4f}** — Low risk of overfitting")
        elif ov < 0.5:
            st.warning(f"Overfitting ratio: **{ov:.4f}** — Moderate overfitting risk")
        else:
            st.error(f"Overfitting ratio: **{ov:.4f}** — High overfitting risk")

        # Metrics comparison table
        st.subheader("In-Sample vs Out-of-Sample Metrics")
        summary = result.summary()
        st.dataframe(summary, use_container_width=True)

        # Cumulative return chart with split line
        split_idx = wf.split_idx
        full_data = df.copy()
        full_perf = Performance(
            full_data, config, result.best_window, result.best_signal,
            fee_bps=fee_bps,
        )
        chart_df = full_perf.data.dropna(subset=["cumu"]).copy()

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=chart_df["datetime"], y=chart_df["cumu"],
            mode="lines", name="Strategy",
        ))
        fig.add_trace(go.Scatter(
            x=chart_df["datetime"], y=chart_df["buy_hold_cumu"],
            mode="lines", name="Buy & Hold",
        ))

        # Vertical line at split point
        if ("datetime" in chart_df.columns
                and split_idx is not None
                and split_idx < len(chart_df)):
            split_date = str(chart_df["datetime"].iloc[split_idx])
            fig.add_vline(
                x=split_date, line_dash="dash", line_color="red",
            )
            fig.add_annotation(
                x=split_date, y=1, yref="paper",
                text="Train/Test Split", showarrow=False,
                xanchor="left", yanchor="top",
                font=dict(color="red"),
            )

        fig.update_layout(
            title=f"{symbol} — Cumulative Return (Walk-Forward)",
            xaxis_title="Date", yaxis_title="Cumulative Return",
            height=500,
        )
        st.plotly_chart(fig, use_container_width=True)

        # Download walk-forward results
        csv = summary.to_csv()
        st.download_button("Download walk-forward results (CSV)", csv,
                           file_name=f"wf_{symbol}.csv", mime="text/csv")
