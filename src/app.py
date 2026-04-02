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
from trade import FutuTrader

setup_logging()
logger = logging.getLogger(__name__)

# ── Registry of available indicators and strategies ─────────────────

INDICATORS = {
    "Bollinger Band (z-score)": "get_bollinger_band",
    "SMA": "get_sma",
    "EMA": "get_ema",
    "RSI": "get_rsi",
    "Stochastic Oscillator": "get_stochastic_oscillator",
}

STRATEGIES = {
    "Momentum": Strategy.momentum_const_signal,
    "Reversion": Strategy.reversion_const_signal,
}

INDICATOR_LABELS = {v: k for k, v in INDICATORS.items()}
STRATEGY_LABELS = {func.__name__: k for k, func in STRATEGIES.items()}
STRATEGY_FUNCS = {func.__name__: func for func in STRATEGIES.values()}

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
    st.subheader("Grid Search Rows")
    st.caption("Each row defines a sweep: factor × indicator × strategy × window range × signal range. "
               "Add rows to combine different configurations.")

    # ── Session state for grid rows ─────────────────────────────────
    _FACTORS = ["price", "volume"]
    _DEFAULT_ROW = {
        "factor": "price",
        "indicator": list(INDICATORS.keys())[0],
        "strategy": list(STRATEGIES.keys())[0],
        "win_min": 5, "win_max": 100, "win_step": 5,
        "sig_min": 0.25, "sig_max": 2.50, "sig_step": 0.25,
    }

    if "grid_rows" not in st.session_state:
        st.session_state["grid_rows"] = [_DEFAULT_ROW.copy()]

    # Render each row
    for idx, row in enumerate(st.session_state["grid_rows"]):
        with st.container(border=True):
            cols_top = st.columns([1.5, 2, 2, 0.5])
            with cols_top[0]:
                row["factor"] = st.selectbox(
                    "Factor", _FACTORS,
                    index=_FACTORS.index(row["factor"]),
                    key=f"gr_factor_{idx}",
                )
            with cols_top[1]:
                ind_keys = list(INDICATORS.keys())
                row["indicator"] = st.selectbox(
                    "Indicator", ind_keys,
                    index=ind_keys.index(row["indicator"])
                    if row["indicator"] in ind_keys else 0,
                    key=f"gr_ind_{idx}",
                )
            with cols_top[2]:
                strat_keys = list(STRATEGIES.keys())
                row["strategy"] = st.selectbox(
                    "Strategy", strat_keys,
                    index=strat_keys.index(row["strategy"])
                    if row["strategy"] in strat_keys else 0,
                    key=f"gr_strat_{idx}",
                )
            with cols_top[3]:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("✕", key=f"gr_del_{idx}",
                             help="Remove this row"):
                    st.session_state["grid_rows"].pop(idx)
                    st.rerun()

            cols_win = st.columns(3)
            with cols_win[0]:
                row["win_min"] = st.number_input(
                    "Win min", value=row["win_min"], min_value=2,
                    key=f"gr_wmin_{idx}")
            with cols_win[1]:
                row["win_max"] = st.number_input(
                    "Win max", value=row["win_max"], min_value=2,
                    key=f"gr_wmax_{idx}")
            with cols_win[2]:
                row["win_step"] = st.number_input(
                    "Win step", value=row["win_step"], min_value=1,
                    key=f"gr_wstep_{idx}")

            cols_sig = st.columns(3)
            with cols_sig[0]:
                row["sig_min"] = st.number_input(
                    "Sig min", value=row["sig_min"], step=0.25,
                    key=f"gr_smin_{idx}")
            with cols_sig[1]:
                row["sig_max"] = st.number_input(
                    "Sig max", value=row["sig_max"], step=0.25,
                    key=f"gr_smax_{idx}")
            with cols_sig[2]:
                row["sig_step"] = st.number_input(
                    "Sig step", value=row["sig_step"], step=0.05,
                    min_value=0.05, key=f"gr_sstep_{idx}")

    if st.button("➕ Add Row", key="gr_add"):
        st.session_state["grid_rows"].append(_DEFAULT_ROW.copy())
        st.rerun()

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
        "volume": price["volume"],
    })


# ── Helpers: build config & row grids (shared by all tabs) ──────────


def _build_config():
    return StrategyConfig(
        indicator_name=INDICATORS[indicator_name],
        strategy_func=STRATEGIES[strategy_name],
        trading_period=trading_period,
    )


def _build_row_grids():
    """Build a list of (config, param_grid) from grid search rows.

    Each sidebar row becomes one param_grid with fixed factor/indicator/strategy
    and its own window × signal ranges.
    """
    row_grids = []
    for row in st.session_state.get("grid_rows", []):
        ind_method = INDICATORS[row["indicator"]]
        strat_func = STRATEGIES[row["strategy"]]
        config = StrategyConfig(
            indicator_name=ind_method,
            strategy_func=strat_func,
            trading_period=trading_period,
        )
        wl = list(range(
            int(row["win_min"]),
            int(row["win_max"]) + 1,
            int(row["win_step"]),
        ))
        sl = list(np.arange(
            row["sig_min"],
            row["sig_max"] + row["sig_step"] / 2,
            row["sig_step"],
        ))
        param_grid = {
            'window': tuple(wl),
            'signal': tuple(sl),
        }
        # Attach row metadata so results carry the factor/indicator/strategy
        meta = {
            'factor': row["factor"],
            'indicator': ind_method,
            'strategy': strat_func.__name__
                if callable(strat_func) else str(strat_func),
        }
        row_grids.append((config, param_grid, meta))
    return row_grids


def _display_label(col, val):
    """Convert internal param values to user-friendly display labels."""
    if col == 'indicator':
        return INDICATOR_LABELS.get(val, val)
    if col == 'strategy':
        return STRATEGY_LABELS.get(val, val)
    if isinstance(val, float):
        return f"{val:.2f}"
    return str(val)


# ── Fetch data ──────────────────────────────────────────────────────

try:
    df = fetch_data(symbol, start_date, end_date)
except Exception as exc:
    logger.error("Failed to fetch data for %s: %s", symbol, exc)
    st.error(f"Failed to fetch data: {exc}")
    st.stop()

st.sidebar.success(f"Loaded {len(df)} daily bars")

# ── Tab layout ──────────────────────────────────────────────────────

tab_full, tab_single, tab_grid, tab_wf, tab_trade = st.tabs(
    ["Full Analysis", "Single Backtest", "Parameter Optimization",
     "Walk-Forward Test", "Trading"]
)

# ── Tab 0: Full Analysis ───────────────────────────────────────────

with tab_full:
    run_full = st.button("Run Full Analysis", type="primary", key="run_full")

    if run_full:
        row_grids = _build_row_grids()
        if not row_grids:
            st.error("No grid search rows configured — add rows in the sidebar.")
            st.stop()

        # ── Step 1: Grid Search ─────────────────────────────────────
        total = sum(
            len(pg['window']) * len(pg['signal']) for _, pg, _ in row_grids
        )
        if total == 0:
            st.error("Grid is empty — check Window/Signal ranges in the sidebar.")
            st.stop()
        if total > 5000:
            st.warning(f"Grid has {total} combinations — this may take a while.")

        progress = st.progress(0, text="Running grid search...")
        all_results = []
        done = 0
        for config, param_grid, meta in row_grids:
            data_copy = df.copy()
            data_copy['factor'] = data_copy[meta['factor']]
            opt = ParametersOptimization(data_copy, config, fee_bps=fee_bps)
            for result in opt.optimize_grid(param_grid):
                result['factor'] = meta['factor']
                result['indicator'] = meta['indicator']
                result['strategy'] = meta['strategy']
                all_results.append(result)
                done += 1
                progress.progress(done / total,
                                  text=f"Evaluated {done}/{total} combinations")
        progress.empty()

        param_perf = pd.DataFrame(all_results)

        # ── Walk-Forward (use first row's config) ───────────────────
        wf_result = None
        wf_split_idx = None
        first_config, first_pg, first_meta = row_grids[0]
        try:
            wf_df = df.copy()
            wf_df['factor'] = wf_df[first_meta['factor']]
            wf = WalkForward(wf_df, split_ratio, first_config, fee_bps=fee_bps)
            wf_result = wf.run(tuple(first_pg['window']), tuple(first_pg['signal']))
            wf_split_idx = wf.split_idx
        except ValueError as exc:
            st.warning(f"Walk-forward skipped: {exc}")

        # Persist to session_state so heatmap clicks survive reruns
        st.session_state["full_param_perf"] = param_perf
        st.session_state["full_row_grids"] = row_grids
        st.session_state["full_fee_bps"] = fee_bps
        st.session_state["full_symbol"] = symbol
        st.session_state["full_wf_result"] = wf_result
        st.session_state["full_wf_split_idx"] = wf_split_idx
        st.session_state["full_df"] = df.copy()

    # ── Render results from session_state ───────────────────────────
    if "full_param_perf" in st.session_state:
        param_perf = st.session_state["full_param_perf"]
        row_grids = st.session_state["full_row_grids"]
        _fee_bps = st.session_state["full_fee_bps"]
        _symbol = st.session_state["full_symbol"]
        wf_result = st.session_state["full_wf_result"]
        wf_split_idx = st.session_state["full_wf_split_idx"]
        _df = st.session_state["full_df"]

        valid = param_perf["sharpe"].dropna()
        if valid.empty:
            st.error("All Sharpe ratios are NaN — check data length vs window sizes.")
            st.stop()
        best = param_perf.loc[valid.idxmax()]
        param_cols = [c for c in param_perf.columns if c != "sharpe"]

        # ── Heatmap with click support ──────────────────────────────
        st.header("1. Parameter Optimization")
        best_parts = [f"{c}={_display_label(c, best[c])}" for c in param_cols]
        st.success(f"**Optimal parameters:** {', '.join(best_parts)}, "
                   f"Sharpe={best['sharpe']:.4f}")

        # Axis selectors for heatmap
        col_y_ax, col_x_ax = st.columns(2)
        with col_y_ax:
            y_axis = st.selectbox(
                "Heatmap Y-axis", param_cols,
                index=param_cols.index("window") if "window" in param_cols else 0,
                key="full_y_axis",
            )
        with col_x_ax:
            x_opts = [c for c in param_cols if c != y_axis]
            x_axis = st.selectbox(
                "Heatmap X-axis", x_opts,
                index=x_opts.index("signal") if "signal" in x_opts else 0,
                key="full_x_axis",
            )

        # Filter dropdowns for remaining dimensions
        filter_dims = [c for c in param_cols if c not in (x_axis, y_axis)]
        filters = {}
        if filter_dims:
            filter_cols_ui = st.columns(len(filter_dims))
            for i, dim in enumerate(filter_dims):
                with filter_cols_ui[i]:
                    unique_vals = sorted(param_perf[dim].unique(), key=str)
                    best_dim_val = best[dim]
                    default_idx = (
                        unique_vals.index(best_dim_val)
                        if best_dim_val in unique_vals else 0
                    )
                    filters[dim] = st.selectbox(
                        f"Filter: {dim}",
                        unique_vals,
                        index=default_idx,
                        format_func=lambda v, d=dim: _display_label(d, v),
                        key=f"full_filter_{dim}",
                    )

        # Apply filters
        hm_data = param_perf.copy()
        for dim, val in filters.items():
            if isinstance(val, float):
                hm_data = hm_data[np.isclose(hm_data[dim], val)]
            else:
                hm_data = hm_data[hm_data[dim] == val]

        pivot = hm_data.pivot(index=y_axis, columns=x_axis, values="sharpe")
        x_labels = [_display_label(x_axis, v) for v in pivot.columns]
        y_labels = [_display_label(y_axis, v) for v in pivot.index]

        title_parts = [f"{_symbol}"]
        if filters:
            title_parts.append(", ".join(
                f"{k}={_display_label(k, v)}" for k, v in filters.items()
            ))
        title_parts.append("Sharpe Heatmap")

        fig_hm = go.Figure(data=go.Heatmap(
            z=pivot.values,
            x=x_labels,
            y=y_labels,
            colorscale="RdYlGn",
            zmid=0,
            text=np.round(pivot.values, 2),
            texttemplate="%{text}",
            hovertemplate=f"{y_axis}: %{{y}}<br>{x_axis}: %{{x}}<br>Sharpe: %{{z:.4f}}",
        ))
        fig_hm.update_layout(
            title=" — ".join(title_parts) + " (click a cell)",
            xaxis_title=x_axis.title(),
            yaxis_title=y_axis.title(),
            height=max(400, len(pivot.index) * 30),
        )

        st.plotly_chart(fig_hm, use_container_width=True)

        # Dynamic parameter selectors
        st.subheader("Select parameters")
        selector_cols = st.columns(len(param_cols))
        selected = {}
        for i, col in enumerate(param_cols):
            with selector_cols[i]:
                unique_vals = sorted(param_perf[col].unique(), key=str)
                best_val = best[col]
                default_idx = (
                    unique_vals.index(best_val)
                    if best_val in unique_vals else 0
                )
                selected[col] = st.selectbox(
                    col.title(), unique_vals,
                    index=default_idx,
                    format_func=lambda v, c=col: _display_label(c, v),
                    key=f"full_sel_{col}",
                )

        # Show Sharpe for the selected combo
        match_filter = pd.Series(True, index=param_perf.index)
        for col, val in selected.items():
            if isinstance(val, float):
                match_filter = match_filter & np.isclose(param_perf[col], val)
            else:
                match_filter = match_filter & (param_perf[col] == val)
        match = param_perf[match_filter]
        if not match.empty:
            sel_sharpe = match.iloc[0]["sharpe"]
            info_parts = [f"{c}={_display_label(c, selected[c])}" for c in param_cols]
            st.info(f"**Selected:** {', '.join(info_parts)}, Sharpe={sel_sharpe:.4f}")

        st.divider()

        # ── Performance for selected params ─────────────────────────
        perf_title_parts = [f"{c}={_display_label(c, selected[c])}" for c in param_cols]
        st.header(f"2. Strategy Performance ({', '.join(perf_title_parts)})")

        perf_df = _df.copy()
        if "factor" in selected:
            perf_df["factor"] = perf_df[selected["factor"]]

        sel_indicator = selected.get("indicator", row_grids[0][0].indicator_name)
        sel_strategy_name = selected.get("strategy", None)
        if sel_strategy_name:
            sel_strategy_func = STRATEGY_FUNCS[sel_strategy_name]
        else:
            sel_strategy_func = row_grids[0][0].strategy_func
        perf_config = StrategyConfig(
            indicator_name=sel_indicator,
            strategy_func=sel_strategy_func,
            trading_period=row_grids[0][0].trading_period,
        )
        perf = Performance(perf_df, perf_config, selected["window"],
                           selected["signal"], fee_bps=_fee_bps)

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
            title=f"{_symbol} — Cumulative Return ({', '.join(perf_title_parts)})",
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
            first_config = row_grids[0][0]
            first_meta = row_grids[0][2]
            wf_perf_df = _df.copy()
            wf_perf_df["factor"] = wf_perf_df[first_meta["factor"]]
            wf_perf = Performance(
                wf_perf_df, first_config, wf_result.best_window,
                wf_result.best_signal, fee_bps=_fee_bps,
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
    single_factor = st.selectbox(
        "Factor", ["price", "volume"],
        key="single_factor",
        help="Data column the indicator operates on.",
    )
    run_single = st.button("Run Backtest", type="primary", key="run_single")

    if run_single:
        data_copy = df.copy()
        data_copy["factor"] = data_copy[single_factor]
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
        row_grids = _build_row_grids()
        if not row_grids:
            st.error("No grid search rows configured — add rows in the sidebar.")
            st.stop()

        total = sum(
            len(pg['window']) * len(pg['signal']) for _, pg, _ in row_grids
        )

        if total == 0:
            st.error("Grid is empty — check Window/Signal ranges in the sidebar.")
            st.stop()

        if total > 5000:
            st.warning(f"Grid has {total} combinations — this may take a while.")

        # Run with progress bar
        progress = st.progress(0, text="Running grid search...")
        all_results = []
        done = 0
        for config, param_grid, meta in row_grids:
            data_copy = df.copy()
            data_copy['factor'] = data_copy[meta['factor']]
            opt = ParametersOptimization(data_copy, config, fee_bps=fee_bps)
            for result in opt.optimize_grid(param_grid):
                result['factor'] = meta['factor']
                result['indicator'] = meta['indicator']
                result['strategy'] = meta['strategy']
                all_results.append(result)
                done += 1
                progress.progress(done / total,
                                  text=f"Evaluated {done}/{total} combinations")

        progress.empty()
        param_perf = pd.DataFrame(all_results)

        # Best parameters
        valid = param_perf["sharpe"].dropna()
        if valid.empty:
            st.error("All Sharpe ratios are NaN — check data length vs window sizes.")
            st.stop()
        best = param_perf.loc[valid.idxmax()]
        param_cols = [c for c in param_perf.columns if c != "sharpe"]
        best_parts = [f"{c}={_display_label(c, best[c])}" for c in param_cols]
        st.success(f"**Best:** {', '.join(best_parts)}, Sharpe={best['sharpe']:.4f}")

        # Top 10 table
        st.subheader("Top 10 Parameter Combinations")
        st.dataframe(
            param_perf.sort_values("sharpe", ascending=False).head(10)
            .reset_index(drop=True),
            use_container_width=True,
        )

        # Heatmap with dynamic axis/filter selection
        st.subheader("Sharpe Ratio Heatmap")

        col_y_ax, col_x_ax = st.columns(2)
        with col_y_ax:
            y_axis = st.selectbox(
                "Heatmap Y-axis", param_cols,
                index=param_cols.index("window") if "window" in param_cols else 0,
                key="grid_y_axis",
            )
        with col_x_ax:
            x_opts = [c for c in param_cols if c != y_axis]
            x_axis = st.selectbox(
                "Heatmap X-axis", x_opts,
                index=x_opts.index("signal") if "signal" in x_opts else 0,
                key="grid_x_axis",
            )

        filter_dims = [c for c in param_cols if c not in (x_axis, y_axis)]
        filters = {}
        if filter_dims:
            filter_cols_ui = st.columns(len(filter_dims))
            for i, dim in enumerate(filter_dims):
                with filter_cols_ui[i]:
                    unique_vals = sorted(param_perf[dim].unique(), key=str)
                    best_dim_val = best[dim]
                    default_idx = (
                        unique_vals.index(best_dim_val)
                        if best_dim_val in unique_vals else 0
                    )
                    filters[dim] = st.selectbox(
                        f"Filter: {dim}",
                        unique_vals,
                        index=default_idx,
                        format_func=lambda v, d=dim: _display_label(d, v),
                        key=f"grid_filter_{dim}",
                    )

        hm_data = param_perf.copy()
        for dim, val in filters.items():
            if isinstance(val, float):
                hm_data = hm_data[np.isclose(hm_data[dim], val)]
            else:
                hm_data = hm_data[hm_data[dim] == val]

        pivot = hm_data.pivot(index=y_axis, columns=x_axis, values="sharpe")
        x_labels = [_display_label(x_axis, v) for v in pivot.columns]
        y_labels = [_display_label(y_axis, v) for v in pivot.index]

        title_parts = [f"{symbol}"]
        if filters:
            title_parts.append(", ".join(
                f"{k}={_display_label(k, v)}" for k, v in filters.items()
            ))
        title_parts.append("Sharpe Heatmap")

        fig_hm = go.Figure(data=go.Heatmap(
            z=pivot.values,
            x=x_labels,
            y=y_labels,
            colorscale="RdYlGn",
            zmid=0,
            text=np.round(pivot.values, 2),
            texttemplate="%{text}",
            hovertemplate=f"{y_axis}: %{{y}}<br>{x_axis}: %{{x}}<br>Sharpe: %{{z:.4f}}",
        ))
        fig_hm.update_layout(
            title=" — ".join(title_parts),
            xaxis_title=x_axis.title(),
            yaxis_title=y_axis.title(),
            height=max(400, len(pivot.index) * 30),
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
        row_grids = _build_row_grids()
        if not row_grids:
            st.error("No grid search rows configured — add rows in the sidebar.")
            st.stop()

        first_config, first_pg, first_meta = row_grids[0]
        window_list = first_pg['window']
        signal_list = first_pg['signal']

        if not window_list or not signal_list:
            st.error("Grid is empty — check Window/Signal ranges in the sidebar.")
            st.stop()

        data_copy = df.copy()
        data_copy['factor'] = data_copy[first_meta['factor']]

        try:
            wf = WalkForward(
                data_copy, split_ratio, first_config, fee_bps=fee_bps,
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
        full_data['factor'] = full_data[first_meta['factor']]
        full_perf = Performance(
            full_data, first_config, result.best_window, result.best_signal,
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

# ── Tab 4: Trading ──────────────────────────────────────────────────

with tab_trade:
    st.header("Futu Trading")
    st.caption("Connect to Futu OpenD to apply backtest strategies to live/paper trading.")

    # ── Trading config ───────────────────────────────────────────
    col_cfg1, col_cfg2, col_cfg3, col_cfg4 = st.columns(4)
    with col_cfg1:
        trade_symbol = st.text_input("Futu Symbol", value="HK.00002",
                                     help="Futu format: US.WEAT, HK.00700",
                                     key="trade_symbol")
    with col_cfg2:
        trade_qty = st.number_input("Quantity (shares)", value=100,
                                    min_value=1, step=1, key="trade_qty")
    with col_cfg3:
        detected_market = FutuTrader.detect_market(trade_symbol)
        trade_market = st.selectbox(
            "Market", list(FutuTrader.MARKET_MAP.keys()),
            index=list(FutuTrader.MARKET_MAP.keys()).index(detected_market)
            if detected_market in FutuTrader.MARKET_MAP else 0,
            key="trade_market",
            help="Auto-detected from symbol prefix",
        )
    with col_cfg4:
        paper_mode = st.toggle("Paper Trading", value=True, key="paper_mode")

    if not paper_mode:
        st.warning("**LIVE TRADING** is enabled. Real orders will be placed.")

    st.divider()

    # ── Connection ───────────────────────────────────────────────
    connect_btn = st.button("Connect to Futu OpenD", type="primary",
                            key="connect_futu")

    if connect_btn:
        try:
            trader = FutuTrader(paper=paper_mode, market=trade_market)
            st.session_state["trader"] = trader
            st.session_state["trader_paper"] = paper_mode
            st.session_state["trader_market"] = trade_market
            st.success("Connected to Futu OpenD "
                       f"({trade_market} market, "
                       f"{'paper' if paper_mode else 'LIVE'} mode)")
        except Exception as exc:
            st.error(f"Connection failed: {exc}")
            logger.error("Futu connection failed: %s", exc)

    if "trader" in st.session_state:
        trader = st.session_state["trader"]
        is_paper = st.session_state.get("trader_paper", True)
        trader_market = st.session_state.get("trader_market", "US")
        mode_label = "PAPER" if is_paper else "LIVE"
        st.info(f"Connected ({trader_market} market, {mode_label} mode)")

        # ── Account & Positions ─────────────────────────────────────
        st.subheader("Account Overview")
        col_acct, col_pos = st.columns(2)

        with col_acct:
            acct = trader.get_account_info()
            if acct is not None and not acct.empty:
                st.dataframe(acct, use_container_width=True)
            else:
                st.caption("No account data available.")

        with col_pos:
            positions = trader.get_positions()
            if positions is not None and not positions.empty:
                st.dataframe(positions, use_container_width=True)
            else:
                st.caption("No open positions.")

        st.divider()

        # ── Manual Order ────────────────────────────────────────────
        st.subheader("Manual Order")
        col_side, col_otype, col_price = st.columns(3)
        with col_side:
            order_side = st.selectbox("Side", ["BUY", "SELL"], key="order_side")
        with col_otype:
            order_type = st.selectbox("Type", ["MARKET", "LIMIT"],
                                     key="order_type")
        with col_price:
            limit_price = st.number_input("Limit Price", value=0.0,
                                          min_value=0.0, step=0.01,
                                          key="limit_price",
                                          disabled=(order_type == "MARKET"))

        if st.button("Place Order", type="primary", key="place_order"):
            ot = "MARKET" if order_type == "MARKET" else "NORMAL"
            price = limit_price if ot == "NORMAL" else None
            result = trader.place_order(
                trade_symbol, trade_qty, order_side,
                order_type=ot, price=price,
            )
            if result.success:
                st.success(f"Order placed: {result.message} (ID: {result.order_id})")
            else:
                st.error(f"Order failed: {result.message}")

        st.divider()

        # ── Apply Strategy Signal ──────────────────────────────────
        st.subheader("Apply Backtest Strategy")
        st.caption(
            "Generate the latest signal from your backtest config and "
            "execute it via Futu."
        )

        col_sw, col_ss = st.columns(2)
        with col_sw:
            strat_window = st.number_input("Window", value=int(window),
                                           min_value=2, key="strat_window")
        with col_ss:
            strat_signal = st.number_input("Signal", value=float(signal),
                                           min_value=0.0, step=0.25,
                                           key="strat_signal")

        if st.button("Generate Signal & Execute", type="primary",
                     key="apply_signal"):
            config = _build_config()
            perf = Performance(df.copy(), config, strat_window, strat_signal,
                               fee_bps=fee_bps)
            latest_signal = perf.data["pos"].dropna().iloc[-1]

            signal_map = {1: "🟢 LONG", -1: "🔴 SHORT", 0: "⚪ FLAT"}
            st.info(f"Latest signal: **{signal_map.get(int(latest_signal), latest_signal)}** "
                    f"(window={strat_window}, signal={strat_signal:.2f})")

            result = trader.apply_signal(
                trade_symbol, latest_signal, trade_qty,
            )
            if result is None:
                st.info("No trade needed — position already matches signal.")
            elif result.success:
                st.success(f"Trade executed: {result.message} (ID: {result.order_id})")
            else:
                st.error(f"Trade failed: {result.message}")

        st.divider()

        # ── Today's Orders ─────────────────────────────────────────
        st.subheader("Today's Orders")
        orders = trader.get_orders()
        if orders is not None and not orders.empty:
            st.dataframe(orders, use_container_width=True)

            # ── Cancel Orders ──────────────────────────────────────
            col_cancel_id, col_cancel_btn, col_cancel_all = st.columns([3, 1, 1])
            with col_cancel_id:
                order_ids = orders["order_id"].astype(str).tolist()
                cancel_id = st.selectbox(
                    "Select order to cancel", order_ids,
                    key="cancel_order_id",
                )
            with col_cancel_btn:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("Cancel Order", key="cancel_single"):
                    if trader.cancel_order(cancel_id):
                        st.success(f"Order {cancel_id} cancelled")
                        st.rerun()
                    else:
                        st.error(f"Failed to cancel order {cancel_id}")
            with col_cancel_all:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("Cancel All Orders", key="cancel_all"):
                    if trader.cancel_all_orders():
                        st.success("All orders cancelled")
                        st.rerun()
                    else:
                        st.error("Failed to cancel all orders")
        else:
            st.caption("No orders today.")

        st.divider()

        # Disconnect button
        if st.button("Disconnect", key="disconnect_futu"):
            trader.close()
            del st.session_state["trader"]
            del st.session_state["trader_paper"]
            st.rerun()
