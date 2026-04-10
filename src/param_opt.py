'''
Parameter optimization for single-factor and multi-factor strategies.

Uses optuna for efficient search:
- GridSampler (exhaustive) when n_trials covers the full parameter space.
- TPESampler (Bayesian / Tree-structured Parzen Estimator) when n_trials
  is smaller than the space — typically for large grids (>10 000 combos).
'''

import itertools
import logging
import math
from dataclasses import dataclass

import numpy as np
import optuna
import pandas as pd
from optuna.samplers import GridSampler, TPESampler

from perf import Performance

logger = logging.getLogger(__name__)

optuna.logging.set_verbosity(optuna.logging.WARNING)

OPTUNA_MAX_TRIALS = 10_000
OPTUNA_SEED = 42


@dataclass
class OptimizeResult:
    """Result returned by ParametersOptimization.optimize() and optimize_multi()."""

    grid_df: pd.DataFrame  # Raw results — NaN preserved, for CSV/heatmap
    best: dict             # Best params by Sharpe (NaN → None)
    top10: list            # Top 10 by Sharpe descending (NaN → None)
    grid: list             # All rows (NaN → None)
    n_valid: int           # Trials with finite Sharpe
    study: object          # optuna.Study — for visualization


class ParametersOptimization:

    def __init__(self, data, config, *, fee_bps=None):
        self.data = data
        self.config = config
        self.fee_bps = fee_bps

    def optimize(self, window_values, signal_values, *, n_trials=None,
                 callbacks=None):
        """Optimize window × signal via optuna.

        Uses GridSampler (exhaustive) when *n_trials* covers the full space,
        TPESampler (Bayesian) otherwise.

        Args:
            window_values: Tuple of candidate window values.
            signal_values: Tuple of candidate signal values.
            n_trials: Number of trials.  Defaults to
                      ``min(total_combinations, OPTUNA_MAX_TRIALS)``.
            callbacks: Optional list of optuna callbacks, each called
                       ``cb(study, trial)`` after every trial.

        Returns:
            pd.DataFrame with columns ``[window, signal, sharpe]``.
        """
        total = len(window_values) * len(signal_values)
        if n_trials is None:
            n_trials = min(total, OPTUNA_MAX_TRIALS)

        search_space = {
            "window": list(window_values),
            "signal": list(signal_values),
        }

        if n_trials >= total:
            sampler = GridSampler(search_space, seed=OPTUNA_SEED)
            n_trials = total
            logger.info("Exhaustive optimization: %d windows × %d signals "
                        "= %d trials (GridSampler)",
                        len(window_values), len(signal_values), total)
        else:
            sampler = TPESampler(seed=OPTUNA_SEED)
            logger.info("Bayesian optimization: %d space, %d trials (TPE)",
                        total, n_trials)

        study = optuna.create_study(direction="maximize", sampler=sampler)

        def objective(trial):
            window = trial.suggest_categorical("window", search_space["window"])
            signal = trial.suggest_categorical("signal", search_space["signal"])
            try:
                perf = Performance(
                    self.data.copy(), self.config,
                    window, signal, fee_bps=self.fee_bps,
                )
                perf.enrich_performance()
                sharpe = perf.get_sharpe_ratio()
                return sharpe if np.isfinite(sharpe) else float("-inf")
            except Exception:
                logger.warning("Optimization failed for window=%s, signal=%s",
                               window, signal, exc_info=True)
                return float("-inf")

        study.optimize(objective, n_trials=n_trials,
                       callbacks=callbacks or [])

        rows = []
        for trial in study.trials:
            if trial.state == optuna.trial.TrialState.COMPLETE:
                sharpe = trial.value if trial.value > float("-inf") else np.nan
                rows.append({
                    "window": trial.params["window"],
                    "signal": trial.params["signal"],
                    "sharpe": sharpe,
                })

        logger.info("Optimization complete: %d trials evaluated", len(rows))
        return self._build_result(pd.DataFrame(rows), study)

    def run(self, window_values, signal_values, *, n_trials=None, callbacks=None):
        """Auto-dispatch to optimize() or optimize_multi() based on config substrategies.

        Mirrors the auto-dispatch pattern in WalkForward.run().
        Single-factor configs call optimize(); multi-factor call optimize_multi().
        """
        subs = self.config.get_substrategies()
        if len(subs) > 1:
            return self.optimize_multi(
                window_values, signal_values,
                n_trials=n_trials, callbacks=callbacks,
            )
        return self.optimize(
            window_values, signal_values,
            n_trials=n_trials, callbacks=callbacks,
        )

    def optimize_multi(self, window_ranges, signal_ranges, *, n_trials=None,
                       callbacks=None):
        """Multi-factor optimization over N-dimensional parameter space.

        Uses GridSampler when *n_trials* covers the full space,
        TPESampler (Bayesian) otherwise.

        Args:
            window_ranges: list of tuples, one per substrategy.
                           e.g. ``[(10, 20, 30), (5, 10, 15)]``
            signal_ranges: list of tuples, one per substrategy.
                           e.g. ``[(0.5, 1.0), (20, 50, 80)]``
            n_trials: Number of trials.  Defaults to
                      ``min(total_combinations, OPTUNA_MAX_TRIALS)``.
            callbacks: Optional list of optuna callbacks, each called
                       ``cb(study, trial)`` after every trial.

        Returns:
            pd.DataFrame with columns ``window_0``, ``signal_0``, …,
            ``window_N``, ``signal_N``, ``sharpe``.
        """
        n_factors = len(window_ranges)
        if len(signal_ranges) != n_factors:
            raise ValueError(
                f"window_ranges has {n_factors} entries but "
                f"signal_ranges has {len(signal_ranges)}"
            )

        per_factor = [
            list(itertools.product(w, s))
            for w, s in zip(window_ranges, signal_ranges)
        ]
        total = math.prod(len(g) for g in per_factor)

        if n_trials is None:
            n_trials = min(total, OPTUNA_MAX_TRIALS)

        search_space = {}
        for i in range(n_factors):
            search_space[f"window_{i}"] = list(window_ranges[i])
            search_space[f"signal_{i}"] = list(signal_ranges[i])

        if n_trials >= total:
            sampler = GridSampler(search_space, seed=OPTUNA_SEED)
            n_trials = total
            logger.info("Exhaustive multi-factor optimization: "
                        "%d factors, %d trials (GridSampler)",
                        n_factors, total)
        else:
            sampler = TPESampler(seed=OPTUNA_SEED)
            logger.info("Bayesian multi-factor optimization: "
                        "%d factors, %d space, %d trials (TPE)",
                        n_factors, total, n_trials)

        study = optuna.create_study(direction="maximize", sampler=sampler)

        def objective(trial):
            windows = []
            signals = []
            for i in range(n_factors):
                w = trial.suggest_categorical(
                    f"window_{i}", search_space[f"window_{i}"],
                )
                s = trial.suggest_categorical(
                    f"signal_{i}", search_space[f"signal_{i}"],
                )
                windows.append(w)
                signals.append(s)

            try:
                perf = Performance(
                    self.data.copy(), self.config,
                    tuple(windows), tuple(signals), fee_bps=self.fee_bps,
                )
                perf.enrich_performance()
                sharpe = perf.get_sharpe_ratio()
                return sharpe if np.isfinite(sharpe) else float("-inf")
            except Exception:
                logger.warning("Optimization failed for windows=%s, signals=%s",
                               windows, signals, exc_info=True)
                return float("-inf")

        study.optimize(objective, n_trials=n_trials,
                       callbacks=callbacks or [])

        rows = []
        for trial in study.trials:
            if trial.state == optuna.trial.TrialState.COMPLETE:
                row = {}
                for i in range(n_factors):
                    row[f"window_{i}"] = trial.params[f"window_{i}"]
                    row[f"signal_{i}"] = trial.params[f"signal_{i}"]
                sharpe = trial.value if trial.value > float("-inf") else np.nan
                row["sharpe"] = sharpe
                rows.append(row)

        logger.info("Multi-factor optimization complete: %d trials evaluated",
                     len(rows))
        return self._build_result(pd.DataFrame(rows), study)


    @staticmethod
    def _build_result(df: pd.DataFrame, study) -> "OptimizeResult":
        valid = int(df["sharpe"].notna().sum())
        sorted_df = df.dropna(subset=["sharpe"]).sort_values("sharpe", ascending=False)
        top10 = sorted_df.head(10).replace({np.nan: None}).to_dict(orient="records")
        best = top10[0] if top10 else {}
        grid = df.replace({np.nan: None}).to_dict(orient="records")
        return OptimizeResult(
            grid_df=df,
            best=best,
            top10=top10,
            grid=grid,
            n_valid=valid,
            study=study,
        )


# ---------- Legacy Cartesian grid search (kept as reference) ----------
#
# GRID_WARN_THRESHOLD = 10_000
#
# def optimize(self, indicator_tuple, strategy_tuple):
#     """Single-factor grid search over window × signal.
#     Yields: (window, signal, sharpe) tuples.
#     """
#     total = len(indicator_tuple) * len(strategy_tuple)
#     logger.info("Starting grid search: %d windows × %d signals = %d combinations",
#                 len(indicator_tuple), len(strategy_tuple), total)
#     for window, signal in itertools.product(indicator_tuple, strategy_tuple):
#         try:
#             perf = Performance(self.data, self.config,
#                                window, signal, fee_bps=self.fee_bps)
#             perf.enrich_performance()
#             sharpe = perf.get_sharpe_ratio()
#         except Exception:
#             logger.warning("Grid search failed for window=%s, signal=%s",
#                            window, signal, exc_info=True)
#             sharpe = np.nan
#         yield (window, signal, sharpe)
#     logger.info("Grid search complete: %d combinations evaluated", total)
#
# def optimize_multi(self, window_ranges, signal_ranges):
#     """Multi-factor grid search over N-dimensional parameter space.
#     Yields: dict with window_0, signal_0, …, window_N, signal_N, sharpe.
#     """
#     n_factors = len(window_ranges)
#     if len(signal_ranges) != n_factors:
#         raise ValueError(
#             f"window_ranges has {n_factors} entries but "
#             f"signal_ranges has {len(signal_ranges)}"
#         )
#     per_factor = [
#         list(itertools.product(w, s))
#         for w, s in zip(window_ranges, signal_ranges)
#     ]
#     total = math.prod(len(g) for g in per_factor)
#     if total > GRID_WARN_THRESHOLD:
#         logger.warning("Large grid: %d combinations (threshold %d). "
#                        "Consider reducing ranges or using Bayesian optimization.",
#                        total, GRID_WARN_THRESHOLD)
#     logger.info("Starting multi-factor grid search: %d factors, %d combinations",
#                  n_factors, total)
#     for combo in itertools.product(*per_factor):
#         windows = tuple(c[0] for c in combo)
#         signals = tuple(c[1] for c in combo)
#         try:
#             perf = Performance(
#                 self.data.copy(), self.config,
#                 windows, signals, fee_bps=self.fee_bps,
#             )
#             perf.enrich_performance()
#             sharpe = perf.get_sharpe_ratio()
#         except Exception:
#             logger.warning("Grid search failed for windows=%s, signals=%s",
#                            windows, signals, exc_info=True)
#             sharpe = np.nan
#         row = {}
#         for i, (w, s) in enumerate(zip(windows, signals)):
#             row[f'window_{i}'] = w
#             row[f'signal_{i}'] = s
#         row['sharpe'] = sharpe
#         yield row
#     logger.info("Multi-factor grid search complete: %d combinations evaluated", total)
    