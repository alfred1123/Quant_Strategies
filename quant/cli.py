'''
Backtest pipeline: fetch data, compute indicators, run strategy,
measure performance, and optimize parameters via grid search.

Usage:
    python -m quant.cli --indicator NAME --strategy NAME --asset NAME [OPTIONS]

Indicator, strategy and asset are ``REFDATA`` names — ``REFDATA.INDICATOR.NAME``,
``REFDATA.SIGNAL_TYPE.NAME`` and ``REFDATA.ASSET_TYPE.NAME`` — read from the
Redis snapshot the API publishes (``REDIS_URL``). The grid search bounds
default to that indicator's ``WIN_*`` / ``SIG_*`` columns, the same defaults
the Backtest drawer offers.

Examples:
    # Bollinger + momentum on BTC-USD, crypto calendar
    python -m quant.cli --indicator bollinger --strategy momentum --asset crypto

    # Equity backtest with custom window/signal
    python -m quant.cli --symbol AAPL --asset equity --indicator sma --strategy reversion \
                   --window 50 --signal 1.5

    # Custom date range + grid search bounds
    python -m quant.cli --indicator bollinger --strategy momentum --asset crypto \
                   --symbol ETH-USD --start 2020-01-01 --end 2026-01-01 \
                   --win-min 10 --win-max 60 --win-step 10

    # Skip grid search (single backtest only)
    python -m quant.cli --indicator bollinger --strategy momentum --asset crypto --no-grid

Options:
    --symbol        Yahoo Finance ticker              (default: BTC-USD)
    --start         Backtest start date YYYY-MM-DD    (default: 2016-01-01)
    --end           Backtest end date YYYY-MM-DD      (default: 2026-04-01)
    --asset         REFDATA.ASSET_TYPE name           (required)
    --indicator     REFDATA.INDICATOR name            (required)
    --strategy      REFDATA.SIGNAL_TYPE name          (required)
    --window        Single backtest window            (default: 20)
    --signal        Single backtest signal threshold   (default: 1.0)
    --no-grid       Skip parameter optimization        (default: False)
    --win-min/max/step   Grid search window range     (default: the indicator's WIN_*)
    --sig-min/max/step   Grid search signal range     (default: the indicator's SIG_*)
    --outdir        Output directory for results       (default: ../results)
'''

import argparse
import logging
import os
import time

import matplotlib
matplotlib.use('Agg')  # non-interactive backend — saves to file instead of plt.show()
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

from quant.data.sources import YahooFinance
from quant.refdata.reader import RedisRefData
from quant.shared.config import get_redis_url
from quant.shared.logging import setup_logging
from quant.strategy.optimizer import ParametersOptimization
from quant.strategy.performance import Performance
from quant.strategy.signals import StrategyConfig, resolve_signal_func
from quant.strategy.walk_forward import WalkForward

logger = logging.getLogger(__name__)


def _refdata_row(rows: list[dict], name: str, table: str) -> dict:
    """The catalog row named *name*, or a ``SystemExit`` naming the valid names."""
    row = next((r for r in rows if r["name"] == name), None)
    if row is None:
        valid = ", ".join(sorted(r["name"] for r in rows))
        raise SystemExit(f"unknown {table} {name!r}; REFDATA.{table.upper()} has: {valid}")
    return row


def _grid_bound(given, default, flag: str):
    """An explicit flag wins; otherwise the indicator's REFDATA column, which must exist."""
    if given is not None:
        return given
    if default is None:
        raise SystemExit(f"{flag} has no REFDATA default for this indicator; pass it explicitly")
    return default


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description='Run a backtest pipeline with grid search optimisation.',
    )

    # Data
    p.add_argument('--symbol', default='BTC-USD',
                   help='Yahoo Finance symbol / internal CUSIP (default: %(default)s)')
    p.add_argument('--start', default='2016-01-01',
                   help='Start date YYYY-MM-DD (default: %(default)s)')
    p.add_argument('--end', default='2026-04-01',
                   help='End date YYYY-MM-DD (default: %(default)s)')
    p.add_argument('--asset', required=True,
                   help='REFDATA.ASSET_TYPE name (e.g. crypto, equity)')

    # Indicator / strategy — REFDATA names, resolved in main()
    p.add_argument('--indicator', required=True,
                   help='REFDATA.INDICATOR name (e.g. bollinger, sma)')
    p.add_argument('--strategy', required=True,
                   help='REFDATA.SIGNAL_TYPE name (e.g. momentum, reversion)')

    # Single backtest
    p.add_argument('--window', type=int, default=20,
                   help='Indicator window for single backtest (default: %(default)s)')
    p.add_argument('--signal', type=float, default=1.0,
                   help='Signal threshold for single backtest (default: %(default)s)')

    # Grid search — bounds default to the indicator's REFDATA.INDICATOR WIN_* / SIG_*
    p.add_argument('--no-grid', action='store_true',
                   help='Skip parameter optimisation grid search')
    p.add_argument('--win-min', type=int, default=None,
                   help='Grid: window min (default: REFDATA.INDICATOR.WIN_MIN)')
    p.add_argument('--win-max', type=int, default=None,
                   help='Grid: window max (default: REFDATA.INDICATOR.WIN_MAX)')
    p.add_argument('--win-step', type=int, default=None,
                   help='Grid: window step (default: REFDATA.INDICATOR.WIN_STEP)')
    p.add_argument('--sig-min', type=float, default=None,
                   help='Grid: signal min (default: REFDATA.INDICATOR.SIG_MIN)')
    p.add_argument('--sig-max', type=float, default=None,
                   help='Grid: signal max (default: REFDATA.INDICATOR.SIG_MAX)')
    p.add_argument('--sig-step', type=float, default=None,
                   help='Grid: signal step (default: REFDATA.INDICATOR.SIG_STEP)')

    # Output
    p.add_argument('--outdir', default='../results',
                   help='Output directory (default: %(default)s)')
    p.add_argument('--verbose', '-v', action='store_true',
                   help='Enable DEBUG-level logging')

    # Costs
    p.add_argument('--fee', type=float, default=10.0,
                   help='Transaction fee in basis points (default: %(default)s)')

    # Walk-forward
    p.add_argument('--walk-forward', action='store_true',
                   help='Run walk-forward overfitting test')
    p.add_argument('--split', type=float, default=0.5,
                   help='Train/test split ratio for walk-forward (default: %(default)s)')

    return p.parse_args(argv)


def _grid_axes(args, indicator_method: str, refdata) -> tuple[tuple, tuple]:
    """``(window_list, signal_list)`` from the flags, or the indicator's REFDATA defaults."""
    d = refdata.get_indicator_defaults()[indicator_method]
    win_min = _grid_bound(args.win_min, d["win_min"], "--win-min")
    win_max = _grid_bound(args.win_max, d["win_max"], "--win-max")
    win_step = _grid_bound(args.win_step, d["win_step"], "--win-step")
    sig_min = _grid_bound(args.sig_min, d["sig_min"], "--sig-min")
    sig_max = _grid_bound(args.sig_max, d["sig_max"], "--sig-max")
    sig_step = _grid_bound(args.sig_step, d["sig_step"], "--sig-step")
    window_list = tuple(range(int(win_min), int(win_max) + 1, int(win_step)))
    signal_list = tuple(np.arange(sig_min, sig_max + sig_step / 2, sig_step))
    return window_list, signal_list


def main(args=None, *, refdata=None):
    """Run the pipeline. ``refdata`` is the REFDATA reader; the Redis snapshot by default."""
    if args is None:
        args = parse_args()

    setup_logging(debug=args.verbose)

    pd.set_option('display.max_rows', None)
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', 1000)

    os.makedirs(args.outdir, exist_ok=True)
    tag = f"{args.symbol.lower().replace('-', '')}_{args.indicator}"

    if refdata is None:
        refdata = RedisRefData(get_redis_url())
    indicator_rows = refdata.get("indicator")
    signal_type_rows = refdata.get("signal_type")
    indicator_method = _refdata_row(indicator_rows, args.indicator, "indicator")["method_name"]
    _refdata_row(signal_type_rows, args.strategy, "signal_type")
    strategy_func = resolve_signal_func(
        args.strategy, indicator_method, indicator_rows, signal_type_rows,
    )
    trading_period = int(
        _refdata_row(refdata.get("asset_type"), args.asset, "asset_type")["trading_period"]
    )

    cusip = args.symbol.lower()
    config = StrategyConfig(
        internal_cusip=cusip,
        indicator_name=indicator_method,
        signal_func=strategy_func,
        trading_period=trading_period,
    )

    t0 = time.time()

    # ── Fetch data ──────────────────────────────────────────────────
    yf = YahooFinance()
    price = yf.get_historical_price(args.symbol, args.start, args.end)

    df = pd.DataFrame({
        'datetime': pd.to_datetime(price['t']),
        'price':    price['v'],
        'factor':   price['v'],
        **{col: price[col] for col in ('Open', 'High', 'Low', 'Close', 'Volume')
           if col in price.columns},
    })
    df = df.set_index('datetime').sort_index()
    logger.info("Loaded %d daily bars: %s → %s",
                len(df), df.index[0], df.index[-1])

    data_dict = {cusip: df}

    # ── Single backtest ─────────────────────────────────────────────
    perf = Performance(data_dict, config, args.window, args.signal,
                       fee_bps=args.fee)
    perf.enrich_performance()

    logger.info("\n=== Strategy Performance "
                "(%s %s / signal %s) ===\n%s",
                args.indicator, args.window, args.signal,
                perf.get_strategy_performance())
    logger.info("\n=== Buy & Hold Performance ===\n%s",
                perf.get_buy_hold_performance())

    perf_path = os.path.join(args.outdir, f'perf_{tag}.csv')
    perf.data.reset_index().to_csv(perf_path, index=False)
    logger.info("Daily PnL saved to %s", perf_path)

    # ── Parameter optimisation ──────────────────────────────────────
    if not args.no_grid:
        window_list, signal_list = _grid_axes(args, indicator_method, refdata)

        param_opt = ParametersOptimization(
            data_dict, config, fee_bps=args.fee,
        )

        opt_result = param_opt.optimize(window_list, signal_list)

        opt_path = os.path.join(args.outdir, f'opt_{tag}.csv')
        opt_result.grid_df.to_csv(opt_path, index=False)
        logger.info("Grid search: %d combinations evaluated", len(opt_result.grid_df))
        logger.info("\n%s", pd.DataFrame(opt_result.top10))

        logger.info("Best: window=%d, signal=%.2f, Sharpe=%.4f",
                    int(opt_result.best['window']), opt_result.best['signal'],
                    opt_result.best['sharpe'])

        # Heatmap
        pivot = opt_result.grid_df.pivot(index='window', columns='signal',
                                         values='sharpe')
        plt.figure(figsize=(12, 8))
        sns.heatmap(pivot, annot=True, fmt='.2f', cmap='RdYlGn', center=0)
        plt.title(f'{args.symbol} {args.indicator} {args.strategy} '
                  f'— Sharpe Ratio Heatmap')
        plt.xlabel('Signal Threshold')
        plt.ylabel('Indicator Window')
        plt.tight_layout()
        heatmap_path = os.path.join(args.outdir, f'heatmap_{tag}.png')
        plt.savefig(heatmap_path, dpi=150)
        logger.info("Heatmap saved to %s", heatmap_path)

    # ── Walk-forward overfitting test ───────────────────────────────
    if args.walk_forward:
        window_list, signal_list = _grid_axes(args, indicator_method, refdata)

        wf_df = pd.DataFrame({
            'datetime': pd.to_datetime(price['t']),
            'price':    price['v'],
            'factor':   price['v'],
        })
        wf_df = wf_df.set_index('datetime').sort_index()
        wf_data_dict = {cusip: wf_df}

        wf = WalkForward(
            wf_data_dict, args.split, config, fee_bps=args.fee,
        )
        result = wf.run(window_list, signal_list)

        logger.info("\n=== Walk-Forward Results ===")
        logger.info("Best params: window=%d, signal=%.2f",
                    result.best_window, result.best_signal)
        logger.info("\n%s", result.summary())

        wf_path = os.path.join(args.outdir, f'wf_{tag}.csv')
        result.summary().to_csv(wf_path)
        logger.info("Walk-forward results saved to %s", wf_path)

    logger.info("Done in %.1fs", time.time() - t0)


if __name__ == '__main__':
    main()
