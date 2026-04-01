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

    # Skip grid search (single backtest only)
    python main.py --no-grid

    # Custom output directory
    python main.py --outdir /tmp/results

Options:
    --symbol        Yahoo Finance ticker              (default: BTC-USD)
    --start         Backtest start date YYYY-MM-DD    (default: 2016-01-01)
    --end           Backtest end date YYYY-MM-DD      (default: 2026-04-01)
    --asset         Asset type: crypto | equity       (default: crypto)
    --indicator     Indicator: bollinger|sma|ema|rsi  (default: bollinger)
    --strategy      Strategy: momentum | reversion    (default: momentum)
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
from strat import Strategy
from log_config import setup_logging
from ta import TechnicalAnalysis

logger = logging.getLogger(__name__)

# ── Registries ──────────────────────────────────────────────────────

INDICATORS = {
    'bollinger': 'get_bollinger_band',
    'sma':       'get_sma',
    'ema':       'get_ema',
    'rsi':       'get_rsi',
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
    p.add_argument('--indicator', default='bollinger',
                   choices=INDICATORS.keys(),
                   help='Technical indicator (default: %(default)s)')
    p.add_argument('--strategy', default='momentum',
                   choices=STRATEGIES.keys(),
                   help='Trading strategy (default: %(default)s)')

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

    # Costs
    p.add_argument('--fee', type=float, default=5.0,
                   help='Transaction fee in basis points (default: %(default)s)')

    return p.parse_args(argv)


def main(args=None):
    if args is None:
        args = parse_args()

    setup_logging(debug=args.verbose)

    pd.set_option('display.max_rows', None)
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', 1000)

    os.makedirs(args.outdir, exist_ok=True)
    tag = f"{args.symbol.lower().replace('-', '')}_{args.indicator}"

    trading_period = ASSET_TRADING_PERIODS[args.asset]
    indicator_method = INDICATORS[args.indicator]
    strategy_func = STRATEGIES[args.strategy]

    t0 = time.time()

    # ── Fetch data ──────────────────────────────────────────────────
    yf = YahooFinance()
    price = yf.get_historical_price(args.symbol, args.start, args.end)

    df = pd.DataFrame({
        'datetime': price['t'],
        'price':    price['v'],
        'factor':   price['v'],
    })
    logger.info("Loaded %d daily bars: %s → %s",
                len(df), df['datetime'].iloc[0], df['datetime'].iloc[-1])

    # ── Technical analysis ──────────────────────────────────────────
    ta = TechnicalAnalysis(df)
    indicator_func = getattr(ta, indicator_method)

    # ── Single backtest ─────────────────────────────────────────────
    perf = Performance(df, trading_period, indicator_func,
                       strategy_func, args.window, args.signal,
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
            ta.data, trading_period, indicator_func, strategy_func,
            fee_bps=args.fee,
        )

        param_perf = pd.DataFrame(
            param_opt.optimize(window_list, signal_list),
            columns=['window', 'signal', 'sharpe'],
        )

        opt_path = os.path.join(args.outdir, f'opt_{tag}.csv')
        param_perf.to_csv(opt_path, index=False)
        logger.info("Grid search: %d combinations evaluated", len(param_perf))
        logger.info("\n%s",
                    param_perf.sort_values('sharpe', ascending=False).head(10))

        best = param_perf.loc[param_perf['sharpe'].idxmax()]
        logger.info("Best: window=%d, signal=%.2f, Sharpe=%.4f",
                    int(best['window']), best['signal'], best['sharpe'])

        # Heatmap
        pivot = param_perf.pivot(index='window', columns='signal',
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

    logger.info("Done in %.1fs", time.time() - t0)


if __name__ == '__main__':
    main()















