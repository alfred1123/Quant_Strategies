'''
Backtest pipeline: fetch data, compute indicators, run strategy,
measure performance, and optimize parameters via grid search.

Usage:
    python -m main [OPTIONS]
    # or: cd src && python main.py [OPTIONS]

Examples:
    # Run with defaults (BTC-USD, Bollinger + Momentum, crypto 365)
    python main.py

    # Equity backtest with custom window/signal
    python main.py --symbol AAPL --asset equity --window 50 --signal 1.5

    # Custom date range + grid search bounds
    python main.py --symbol ETH-USD --start 2020-01-01 --end 2026-01-01 \
                   --win-min 10 --win-max 60 --win-step 10

    # Different indicator + strategy combination
    python main.py --indicator sma --strategy reversion

    # Optimize over both price and volume as factor
    python main.py --factor price volume

    # Skip grid search (single backtest only)
    python main.py --no-grid

    # Custom output directory
    python main.py --outdir /tmp/results

Options:
    --symbol        Yahoo Finance ticker              (default: BTC-USD)
    --start         Backtest start date YYYY-MM-DD    (default: 2016-01-01)
    --end           Backtest end date YYYY-MM-DD      (default: 2026-04-01)
    --asset         Asset type: crypto | equity       (default: crypto)
    --indicator     Indicator(s): bollinger|sma|ema|rsi  (default: bollinger)
                     Multiple values sweep across indicators in grid search
    --strategy      Strategy(ies): momentum | reversion  (default: momentum)
                     Multiple values sweep across strategies in grid search
    --factor        Factor: price | volume (multi ok)  (default: price)
    --window        Single backtest window            (default: 20)
    --signal        Single backtest signal threshold   (default: 1.0)
    --no-grid       Skip parameter optimization        (default: False)
    --win-min/max/step   Grid search window range     (default: 5/100/5)
    --sig-min/max/step   Grid search signal range     (default: 0.25/2.50/0.25)
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

from data import YahooFinance
from param_opt import ParametersOptimization
from perf import Performance
from strat import Strategy, StrategyConfig
from log_config import setup_logging
from walk_forward import WalkForward

logger = logging.getLogger(__name__)

# ── Registries ──────────────────────────────────────────────────────

INDICATORS = {
    'bollinger':  'get_bollinger_band',
    'sma':        'get_sma',
    'ema':        'get_ema',
    'rsi':        'get_rsi',
    'stochastic': 'get_stochastic_oscillator',
}

STRATEGIES = {
    'momentum':  Strategy.momentum_const_signal,
    'reversion': Strategy.reversion_const_signal,
}

ASSET_TRADING_PERIODS = {
    'crypto': 365,   # 24/7/365
    'equity': 252,   # NYSE/NASDAQ trading days
}


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description='Run a backtest pipeline with grid search optimisation.',
    )

    # Data
    p.add_argument('--symbol', default='BTC-USD',
                   help='Yahoo Finance ticker (default: %(default)s)')
    p.add_argument('--start', default='2016-01-01',
                   help='Start date YYYY-MM-DD (default: %(default)s)')
    p.add_argument('--end', default='2026-04-01',
                   help='End date YYYY-MM-DD (default: %(default)s)')
    p.add_argument('--asset', default='crypto',
                   choices=ASSET_TRADING_PERIODS.keys(),
                   help='Asset type (default: %(default)s)')

    # Indicator / strategy
    p.add_argument('--indicator', nargs='+', default=['bollinger'],
                   choices=INDICATORS.keys(),
                   help='Technical indicator(s) — multiple values sweep in '
                        'grid search (default: %(default)s)')
    p.add_argument('--strategy', nargs='+', default=['momentum'],
                   choices=STRATEGIES.keys(),
                   help='Trading strategy(ies) — multiple values sweep in '
                        'grid search (default: %(default)s)')

    # Single backtest
    p.add_argument('--window', type=int, default=20,
                   help='Indicator window for single backtest (default: %(default)s)')
    p.add_argument('--signal', type=float, default=1.0,
                   help='Signal threshold for single backtest (default: %(default)s)')

    # Grid search
    p.add_argument('--no-grid', action='store_true',
                   help='Skip parameter optimisation grid search')
    p.add_argument('--win-min', type=int, default=5,
                   help='Grid: window min (default: %(default)s)')
    p.add_argument('--win-max', type=int, default=100,
                   help='Grid: window max (default: %(default)s)')
    p.add_argument('--win-step', type=int, default=5,
                   help='Grid: window step (default: %(default)s)')
    p.add_argument('--sig-min', type=float, default=0.25,
                   help='Grid: signal min (default: %(default)s)')
    p.add_argument('--sig-max', type=float, default=2.50,
                   help='Grid: signal max (default: %(default)s)')
    p.add_argument('--sig-step', type=float, default=0.25,
                   help='Grid: signal step (default: %(default)s)')

    # Output
    p.add_argument('--outdir', default='../results',
                   help='Output directory (default: %(default)s)')
    p.add_argument('--verbose', '-v', action='store_true',
                   help='Enable DEBUG-level logging')

    # Factor
    p.add_argument('--factor', nargs='+', default=['price'],
                   choices=['price', 'volume'],
                   help='Data column(s) to use as the indicator factor. '
                        'Multiple values sweep over each in grid search '
                        '(default: %(default)s)')

    # Costs
    p.add_argument('--fee', type=float, default=5.0,
                   help='Transaction fee in basis points (default: %(default)s)')

    # Walk-forward
    p.add_argument('--walk-forward', action='store_true',
                   help='Run walk-forward overfitting test')
    p.add_argument('--split', type=float, default=0.5,
                   help='Train/test split ratio for walk-forward (default: %(default)s)')

    return p.parse_args(argv)


def main(args=None):
    if args is None:
        args = parse_args()

    setup_logging(debug=args.verbose)

    pd.set_option('display.max_rows', None)
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', 1000)

    os.makedirs(args.outdir, exist_ok=True)
    tag = f"{args.symbol.lower().replace('-', '')}_{args.indicator[0]}"

    trading_period = ASSET_TRADING_PERIODS[args.asset]
    indicator_method = INDICATORS[args.indicator[0]]
    strategy_func = STRATEGIES[args.strategy[0]]

    config = StrategyConfig(
        indicator_name=indicator_method,
        strategy_func=strategy_func,
        trading_period=trading_period,
    )

    t0 = time.time()

    # ── Fetch data ──────────────────────────────────────────────────
    yf = YahooFinance()
    price = yf.get_historical_price(args.symbol, args.start, args.end)

    df = pd.DataFrame({
        'datetime': price['t'],
        'price':    price['v'],
        'factor':   price['v'],
        'volume':   price['volume'],
    })

    # Override factor column for single backtest when a single factor is chosen
    if len(args.factor) == 1 and args.factor[0] != 'price':
        df['factor'] = df[args.factor[0]]

    logger.info("Loaded %d daily bars: %s → %s",
                len(df), df['datetime'].iloc[0], df['datetime'].iloc[-1])

    # ── Single backtest ─────────────────────────────────────────────
    perf = Performance(df, config, args.window, args.signal,
                       fee_bps=args.fee)

    logger.info("\n=== Strategy Performance "
                "(%s %s / signal %s) ===\n%s",
                args.indicator, args.window, args.signal,
                perf.get_strategy_performance())
    logger.info("\n=== Buy & Hold Performance ===\n%s",
                perf.get_buy_hold_performance())

    perf_path = os.path.join(args.outdir, f'perf_{tag}.csv')
    perf.data.to_csv(perf_path, index=False)
    logger.info("Daily PnL saved to %s", perf_path)

    # ── Parameter optimisation ──────────────────────────────────────
    if not args.no_grid:
        window_list = tuple(range(args.win_min, args.win_max + 1, args.win_step))
        signal_list = tuple(np.arange(args.sig_min,
                                      args.sig_max + args.sig_step / 2,
                                      args.sig_step))

        param_opt = ParametersOptimization(
            df.copy(), config, fee_bps=args.fee,
        )

        param_grid = {
            'window': window_list,
            'signal': signal_list,
        }
        if len(args.indicator) > 1:
            param_grid['indicator'] = [INDICATORS[i] for i in args.indicator]
        if len(args.strategy) > 1:
            param_grid['strategy'] = [STRATEGIES[s] for s in args.strategy]
        if len(args.factor) > 1:
            param_grid['factor'] = args.factor

        param_perf = pd.DataFrame(param_opt.optimize_grid(param_grid))

        opt_path = os.path.join(args.outdir, f'opt_{tag}.csv')
        param_perf.to_csv(opt_path, index=False)
        logger.info("Grid search: %d combinations evaluated", len(param_perf))
        logger.info("\n%s",
                    param_perf.sort_values('sharpe', ascending=False).head(10))

        best = param_perf.loc[param_perf['sharpe'].idxmax()]
        param_cols = [c for c in param_perf.columns if c != 'sharpe']
        best_parts = [f"{c}={best[c]}" for c in param_cols]
        best_msg = f"Best: {', '.join(best_parts)}, Sharpe={best['sharpe']:.4f}"
        logger.info(best_msg)

        # Heatmap — one per unique combination of non-axis dimensions
        extra_cols = [c for c in param_cols
                      if c not in ('window', 'signal')]

        if extra_cols:
            groups = param_perf.groupby(extra_cols)
        else:
            groups = [(None, param_perf)]

        for group_key, subset in groups:
            if group_key is not None:
                if not isinstance(group_key, tuple):
                    group_key = (group_key,)
                suffix = "_" + "_".join(str(v) for v in group_key)
                title_extra = " (" + ", ".join(
                    f"{k}={v}" for k, v in zip(extra_cols, group_key)
                ) + ")"
            else:
                suffix = ""
                title_extra = ""
            pivot = subset.pivot(index='window', columns='signal',
                                 values='sharpe')
            plt.figure(figsize=(12, 8))
            sns.heatmap(pivot, annot=True, fmt='.2f', cmap='RdYlGn', center=0)
            plt.title(f'{args.symbol} — Sharpe Ratio Heatmap{title_extra}')
            plt.xlabel('Signal Threshold')
            plt.ylabel('Indicator Window')
            plt.tight_layout()
            heatmap_path = os.path.join(args.outdir,
                                        f'heatmap_{tag}{suffix}.png')
            plt.savefig(heatmap_path, dpi=150)
            logger.info("Heatmap saved to %s", heatmap_path)

    # ── Walk-forward overfitting test ───────────────────────────────
    if args.walk_forward:
        window_list = tuple(range(args.win_min, args.win_max + 1, args.win_step))
        signal_list = tuple(np.arange(args.sig_min,
                                      args.sig_max + args.sig_step / 2,
                                      args.sig_step))

        wf_df = pd.DataFrame({
            'datetime': price['t'],
            'price':    price['v'],
            'factor':   price['v'],
            'volume':   price['volume'],
        })

        wf = WalkForward(
            wf_df, args.split, config, fee_bps=args.fee,
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















