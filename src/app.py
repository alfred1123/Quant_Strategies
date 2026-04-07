"""Streamlit UI for the backtest pipeline.

Launch:
    cd src && streamlit run app.py
"""

import logging
import math
import sys
import os

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import optuna.visualization as optuna_vis

from data import YahooFinance, AlphaVantage
from strat import SignalDirection, StrategyConfig, SubStrategy, INDICATOR_DEFAULTS
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

STRATEGY_FUNCS = {
    "Momentum": SignalDirection.momentum_const_signal,
    "Reversion": SignalDirection.reversion_const_signal,
}

STRATEGY_NAMES = {
    "Momentum": "momentum_const_signal",
    "Reversion": "reversion_const_signal",
}

ASSET_TYPES = {
    "Crypto (365 days/year)": 365,
    "Equity (252 trading days/year)": 252,
}

DATA_COLUMNS = {
    "Price (close)": "price",
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

    st.divider()
    st.subheader("Costs")
    fee_bps = st.number_input("Transaction fee (bps)", value=5.0,
                              min_value=0.0, max_value=100.0, step=0.5,
                              help="Fee in basis points per unit of turnover "
                                   "(1 bp = 0.01%).")

    # ── Single-factor config ────────────────────────────────────────
    st.divider()
    st.subheader("Single-Factor Strategy")

    indicator_name = st.selectbox("Indicator", list(INDICATORS.keys()))
    strategy_name = st.selectbox("Strategy", list(STRATEGY_FUNCS.keys()))

    st.caption("Single Backtest")
    window = st.number_input("Window", min_value=2, max_value=500, value=20)
    signal = st.number_input("Signal threshold", min_value=0.0,
                             max_value=10.0, value=1.0, step=0.25)

    st.caption("Grid Search Ranges")
    _ind_def = INDICATOR_DEFAULTS.get(INDICATORS[indicator_name], {})
    col_w, col_s = st.columns(2)
    with col_w:
        win_min = st.number_input("Window min",
                                  value=_ind_def.get("win_min", 5),
                                  min_value=2)
        win_max = st.number_input("Window max",
                                  value=_ind_def.get("win_max", 100),
                                  min_value=2)
        win_step = st.number_input("Window step",
                                   value=_ind_def.get("win_step", 5),
                                   min_value=1)
    with col_s:
        sig_min = st.number_input("Signal min",
                                  value=_ind_def.get("sig_min", 0.25),
                                  step=0.25)
        sig_max = st.number_input("Signal max",
                                  value=_ind_def.get("sig_max", 2.50),
                                  step=0.25)
        sig_step = st.number_input("Signal step",
                                   value=_ind_def.get("sig_step", 0.25),
                                   step=0.05, min_value=0.05)

    # ── Multi-factor config ─────────────────────────────────────────
    st.divider()
    st.subheader("Multi-Factor Strategy")

    conjunction = st.radio("Conjunction", ["AND", "OR"],
                           help="AND = all factors agree; OR = any factor signals.")

    if "n_factors" not in st.session_state:
        st.session_state.n_factors = 2

    col_add, col_remove = st.columns(2)
    with col_add:
        if st.button("Add Factor"):
            st.session_state.n_factors += 1
    with col_remove:
        if st.button("Remove Factor") and st.session_state.n_factors > 2:
            st.session_state.n_factors -= 1

    factors = []
    for i in range(st.session_state.n_factors):
        st.caption(f"Factor {i + 1}")
        f_indicator = st.selectbox(f"Indicator##f{i}", list(INDICATORS.keys()),
                                   key=f"f_ind_{i}")
        f_strategy = st.selectbox(f"Strategy##f{i}", list(STRATEGY_FUNCS.keys()),
                                  key=f"f_strat_{i}")
        f_data_col = st.selectbox(f"Data column##f{i}", list(DATA_COLUMNS.keys()),
                                  key=f"f_dcol_{i}")
        _f_def = INDICATOR_DEFAULTS.get(INDICATORS[f_indicator], {})
        f_col_w, f_col_s = st.columns(2)
        with f_col_w:
            f_win_min = st.number_input(f"Win min##f{i}",
                                        value=_f_def.get("win_min", 5),
                                        min_value=2, key=f"f_wmin_{i}")
            f_win_max = st.number_input(f"Win max##f{i}",
                                        value=_f_def.get("win_max", 50),
                                        min_value=2, key=f"f_wmax_{i}")
            f_win_step = st.number_input(f"Win step##f{i}",
                                         value=_f_def.get("win_step", 5),
                                         min_value=1, key=f"f_wstep_{i}")
        with f_col_s:
            f_sig_min = st.number_input(f"Sig min##f{i}",
                                        value=_f_def.get("sig_min", 0.25),
                                        step=0.25, key=f"f_smin_{i}")
            f_sig_max = st.number_input(f"Sig max##f{i}",
                                        value=_f_def.get("sig_max", 2.50),
                                        step=0.25, key=f"f_smax_{i}")
            f_sig_step = st.number_input(f"Sig step##f{i}",
                                         value=_f_def.get("sig_step", 0.25),
                                         step=0.05, min_value=0.05,
                                         key=f"f_sstep_{i}")
        factors.append({
            "indicator": INDICATORS[f_indicator],
            "strategy_func": STRATEGY_FUNCS[f_strategy],
            "strategy_func_name": STRATEGY_NAMES[f_strategy],
            "data_column": DATA_COLUMNS[f_data_col],
            "win_min": f_win_min, "win_max": f_win_max, "win_step": f_win_step,
            "sig_min": f_sig_min, "sig_max": f_sig_max, "sig_step": f_sig_step,
        })

    # ── Walk-forward ────────────────────────────────────────────────
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


# ── Fetch data ──────────────────────────────────────────────────────

try:
    df = fetch_data(symbol, start_date, end_date)
except Exception as exc:
    logger.error("Failed to fetch data for %s: %s", symbol, exc)
    st.error(f"Failed to fetch data: {exc}")
    st.stop()

st.sidebar.success(f"Loaded {len(df)} daily bars")

# ── Helper: optuna visualization sub-section ────────────────────────

def render_optuna_plots(study, title_prefix):
    """Render contour, param importances, and optimization history."""
    st.subheader(f"{title_prefix} — Optuna Visualizations")

    viz_tabs = st.tabs([
        "Contour (Heatmap)", "Param Importances", "Optimization History",
    ])

    with viz_tabs[0]:
        try:
            fig = optuna_vis.plot_contour(study)
            fig.update_layout(title=f"{title_prefix} — Contour Plot",
                              height=600)
            st.plotly_chart(fig, use_container_width=True)
        except Exception as exc:
            st.warning(f"Contour plot unavailable: {exc}")

    with viz_tabs[1]:
        try:
            fig = optuna_vis.plot_param_importances(study)
            fig.update_layout(title=f"{title_prefix} — Parameter Importances",
                              height=500)
            st.plotly_chart(fig, use_container_width=True)
        except Exception as exc:
            st.warning(f"Parameter importances unavailable: {exc}")

    with viz_tabs[2]:
        try:
            fig = optuna_vis.plot_optimization_history(study)
            fig.update_layout(title=f"{title_prefix} — Optimization History",
                              height=500)
            st.plotly_chart(fig, use_container_width=True)
        except Exception as exc:
            st.warning(f"Optimization history unavailable: {exc}")

# ── Tab layout ──────────────────────────────────────────────────────

tab_single, tab_grid, tab_multi, tab_wf = st.tabs([
    "Single Backtest",
    "Parameter Optimization",
    "Multi-Factor Optimization",
    "Walk-Forward Test",
])

# ── Tab 1: Single backtest ──────────────────────────────────────────

with tab_single:
    run_single = st.button("Run Backtest", type="primary", key="run_single")

    if run_single:
        data_copy = df.copy()
        config = StrategyConfig(
            ticker=symbol,
            indicator_name=INDICATORS[indicator_name],
            signal_func=STRATEGY_FUNCS[strategy_name],
            trading_period=trading_period,
        )

        perf = Performance(data_copy, config, window, signal,
                           fee_bps=fee_bps)
        perf.enrich_performance()

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

# ── Tab 2: Single-factor parameter optimization ────────────────────

with tab_grid:
    run_grid = st.button("Run Optimization", type="primary", key="run_grid")

    if run_grid:
        window_list = list(range(int(win_min), int(win_max) + 1, int(win_step)))
        signal_list = list(np.arange(sig_min, sig_max + sig_step / 2, sig_step))
        total = len(window_list) * len(signal_list)

        if total > 5000:
            st.warning(f"Grid has {total} combinations — this may take a while.")

        data_copy = df.copy()
        config = StrategyConfig(
            ticker=symbol,
            indicator_name=INDICATORS[indicator_name],
            signal_func=STRATEGY_FUNCS[strategy_name],
            trading_period=trading_period,
        )

        opt = ParametersOptimization(data_copy, config, fee_bps=fee_bps)

        progress_bar = st.progress(0, text=f"Trial 0 / {total}")
        completed = [0]

        def _on_trial(study, trial):
            completed[0] += 1
            progress_bar.progress(
                completed[0] / total,
                text=f"Trial {completed[0]} / {total}",
            )

        param_perf = opt.optimize(
            tuple(window_list), tuple(signal_list),
            callbacks=[_on_trial],
        )
        progress_bar.empty()

        # Summary counts
        n_valid = param_perf["sharpe"].notna().sum()
        n_nan = param_perf["sharpe"].isna().sum()
        st.info(f"**{total}** trials completed — "
                f"**{n_valid}** valid, **{n_nan}** undefined Sharpe")

        # Best parameters
        if n_valid == 0:
            st.error("No valid Sharpe ratios found. Try wider parameter "
                     "ranges or a different indicator/strategy.")
        else:
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

        # Optuna visualizations
        if opt.last_study is not None:
            render_optuna_plots(opt.last_study,
                                f"{symbol} {indicator_name} + {strategy_name}")

        # Download grid results
        csv = param_perf.to_csv(index=False)
        st.download_button("Download grid results (CSV)", csv,
                           file_name=f"opt_{symbol}.csv", mime="text/csv")

# ── Tab 3: Multi-factor parameter optimization ─────────────────────

with tab_multi:
    run_multi = st.button("Run Multi-Factor Optimization", type="primary",
                          key="run_multi")

    if run_multi:
        substrategies = []
        window_ranges = []
        signal_ranges = []
        for i, f in enumerate(factors):
            substrategies.append(SubStrategy(
                indicator_name=f["indicator"],
                signal_func_name=f["strategy_func_name"],
                window=0,
                signal=0.0,
                data_column=f["data_column"],
            ))
            window_ranges.append(
                tuple(range(int(f["win_min"]),
                            int(f["win_max"]) + 1,
                            int(f["win_step"])))
            )
            signal_ranges.append(
                tuple(np.arange(f["sig_min"],
                                f["sig_max"] + f["sig_step"] / 2,
                                f["sig_step"]))
            )

        config = StrategyConfig(
            ticker=symbol,
            indicator_name=factors[0]["indicator"],
            signal_func=factors[0]["strategy_func"],
            trading_period=trading_period,
            conjunction=conjunction,
            substrategies=tuple(substrategies),
        )

        total = math.prod(
            len(w) * len(s) for w, s in zip(window_ranges, signal_ranges)
        )

        if total > 5000:
            st.warning(f"Multi-factor grid has {total} combinations — "
                       "this may take a while.")

        data_copy = df.copy()
        opt = ParametersOptimization(data_copy, config, fee_bps=fee_bps)

        progress_bar = st.progress(0, text=f"Trial 0 / {total}")
        completed = [0]

        def _on_trial_multi(study, trial):
            completed[0] += 1
            progress_bar.progress(
                completed[0] / total,
                text=f"Trial {completed[0]} / {total}",
            )

        param_perf = opt.optimize_multi(
            window_ranges, signal_ranges,
            callbacks=[_on_trial_multi],
        )
        progress_bar.empty()

        # Summary counts
        n_valid = param_perf["sharpe"].notna().sum()
        n_nan = param_perf["sharpe"].isna().sum()
        st.info(f"**{total}** trials completed — "
                f"**{n_valid}** valid, **{n_nan}** undefined Sharpe")

        if n_valid == 0:
            st.error("No valid Sharpe ratios found. Try wider parameter "
                     "ranges or different indicators/strategies.")
        else:
            best = param_perf.loc[param_perf["sharpe"].idxmax()]
            parts = []
            for i in range(len(factors)):
                parts.append(
                    f"F{i + 1}: window={int(best[f'window_{i}'])}, "
                    f"signal={best[f'signal_{i}']:.2f}"
                )
            st.success(
                f"**Best ({conjunction}):** {' | '.join(parts)}, "
                f"Sharpe={best['sharpe']:.4f}"
            )

        st.subheader("Top 10 Parameter Combinations")
        st.dataframe(
            param_perf.sort_values("sharpe", ascending=False).head(10)
            .reset_index(drop=True),
            use_container_width=True,
        )

        # Optuna visualizations
        if opt.last_study is not None:
            st.subheader("Optuna Visualizations")

            viz_tabs = st.tabs([
                "Contour (per factor pair)",
                "Parallel Coordinates",
                "Param Importances",
                "Optimization History",
            ])

            with viz_tabs[0]:
                for i in range(len(factors)):
                    try:
                        fig = optuna_vis.plot_contour(
                            opt.last_study,
                            params=[f"window_{i}", f"signal_{i}"],
                        )
                        fig.update_layout(
                            title=f"Factor {i + 1} — Contour",
                            height=500,
                        )
                        st.plotly_chart(fig, use_container_width=True)
                    except Exception as exc:
                        st.warning(f"Factor {i + 1} contour unavailable: {exc}")

            with viz_tabs[1]:
                try:
                    fig = optuna_vis.plot_parallel_coordinate(opt.last_study)
                    fig.update_layout(
                        title="Multi-Factor — Parallel Coordinates",
                        height=600,
                    )
                    st.plotly_chart(fig, use_container_width=True)
                except Exception as exc:
                    st.warning(f"Parallel coordinates unavailable: {exc}")

            with viz_tabs[2]:
                try:
                    fig = optuna_vis.plot_param_importances(opt.last_study)
                    fig.update_layout(
                        title="Multi-Factor — Parameter Importances",
                        height=500,
                    )
                    st.plotly_chart(fig, use_container_width=True)
                except Exception as exc:
                    st.warning(f"Parameter importances unavailable: {exc}")

            with viz_tabs[3]:
                try:
                    fig = optuna_vis.plot_optimization_history(opt.last_study)
                    fig.update_layout(
                        title="Multi-Factor — Optimization History",
                        height=500,
                    )
                    st.plotly_chart(fig, use_container_width=True)
                except Exception as exc:
                    st.warning(f"Optimization history unavailable: {exc}")

        csv = param_perf.to_csv(index=False)
        st.download_button("Download multi-factor results (CSV)", csv,
                           file_name=f"opt_multi_{symbol}.csv", mime="text/csv")

# ── Tab 4: Walk-forward overfitting test ───────────────────────────

with tab_wf:
    wf_mode = st.radio("Walk-forward mode",
                       ["Single-factor", "Multi-factor"],
                       key="wf_mode", horizontal=True)

    run_wf = st.button("Run Walk-Forward Test", type="primary", key="run_wf")

    if run_wf:
        data_copy = df.copy()

        if wf_mode == "Single-factor":
            window_list = list(range(int(win_min), int(win_max) + 1,
                                     int(win_step)))
            signal_list = list(np.arange(sig_min, sig_max + sig_step / 2,
                                         sig_step))

            config = StrategyConfig(
                ticker=symbol,
                indicator_name=INDICATORS[indicator_name],
                signal_func=STRATEGY_FUNCS[strategy_name],
                trading_period=trading_period,
            )

            try:
                wf = WalkForward(data_copy, split_ratio, config,
                                 fee_bps=fee_bps)
            except ValueError as exc:
                st.error(f"Walk-forward setup failed: {exc}")
                st.stop()

            with st.spinner("Running walk-forward test "
                            "(optimization on in-sample)..."):
                result = wf.run(tuple(window_list), tuple(signal_list))

            st.success(
                f"**Best params (in-sample):** window={result.best_window}, "
                f"signal={result.best_signal:.2f}"
            )

            best_w = result.best_window
            best_s = result.best_signal

        else:  # Multi-factor walk-forward
            substrategies = []
            window_ranges = []
            signal_ranges = []
            for i, f in enumerate(factors):
                substrategies.append(SubStrategy(
                    indicator_name=f["indicator"],
                    signal_func_name=f["strategy_func_name"],
                    window=0,
                    signal=0.0,
                    data_column=f["data_column"],
                ))
                window_ranges.append(
                    tuple(range(int(f["win_min"]),
                                int(f["win_max"]) + 1,
                                int(f["win_step"])))
                )
                signal_ranges.append(
                    tuple(np.arange(f["sig_min"],
                                    f["sig_max"] + f["sig_step"] / 2,
                                    f["sig_step"]))
                )

            config = StrategyConfig(
                ticker=symbol,
                indicator_name=factors[0]["indicator"],
                signal_func=factors[0]["strategy_func"],
                trading_period=trading_period,
                conjunction=conjunction,
                substrategies=tuple(substrategies),
            )

            try:
                wf = WalkForward(data_copy, split_ratio, config,
                                 fee_bps=fee_bps)
            except ValueError as exc:
                st.error(f"Walk-forward setup failed: {exc}")
                st.stop()

            with st.spinner("Running multi-factor walk-forward test..."):
                result = wf.run_multi(window_ranges, signal_ranges)

            parts = []
            for i in range(len(factors)):
                parts.append(
                    f"F{i + 1}: window={result.best_window[i]}, "
                    f"signal={result.best_signal[i]:.2f}"
                )
            st.success(
                f"**Best params (in-sample, {conjunction}):** "
                f"{' | '.join(parts)}"
            )

            best_w = result.best_window
            best_s = result.best_signal

        # Overfitting ratio with colour coding
        ov = result.overfitting_ratio
        if np.isnan(ov):
            st.warning("Overfitting ratio: N/A "
                       "(in-sample Sharpe is zero or NaN)")
        elif ov < 0.3:
            st.success(f"Overfitting ratio: **{ov:.4f}** — "
                       "Low risk of overfitting")
        elif ov < 0.5:
            st.warning(f"Overfitting ratio: **{ov:.4f}** — "
                       "Moderate overfitting risk")
        else:
            st.error(f"Overfitting ratio: **{ov:.4f}** — "
                     "High overfitting risk")

        # Metrics comparison table
        st.subheader("In-Sample vs Out-of-Sample Metrics")
        summary = result.summary()
        st.dataframe(summary, use_container_width=True)

        # Cumulative return chart with split line
        split_idx = wf.split_idx
        full_data = df.copy()
        full_perf = Performance(
            full_data, config, best_w, best_s,
            fee_bps=fee_bps,
        )
        full_perf.enrich_performance()
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

        if "datetime" in chart_df.columns and split_idx < len(chart_df):
            split_date = pd.Timestamp(chart_df["datetime"].iloc[split_idx])
            fig.add_vline(
                x=split_date, line_dash="dash", line_color="red",
                annotation_text="Train/Test Split",
                annotation_position="top right",
            )

        fig.update_layout(
            title=f"{symbol} — Cumulative Return (Walk-Forward)",
            xaxis_title="Date", yaxis_title="Cumulative Return",
            height=500,
        )
        st.plotly_chart(fig, use_container_width=True)

        csv = summary.to_csv()
        st.download_button("Download walk-forward results (CSV)", csv,
                           file_name=f"wf_{symbol}.csv", mime="text/csv")
