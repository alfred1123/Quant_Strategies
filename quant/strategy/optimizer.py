'''
Parameter optimization for single-factor and multi-factor strategies.

ExhaustiveSearch walks the Cartesian product and records each trial into
an optuna study (for plots). BayesianSearch uses TPE when n_trials is
smaller than the space — typically for large grids (>10 000 combos).
'''

import itertools
import logging
import math
from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np
import optuna
import pandas as pd
from optuna.distributions import CategoricalDistribution
from optuna.samplers import TPESampler
from optuna.trial import create_trial

from quant.strategy.objective import Objective

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

    def best_params(self) -> tuple:
        """``(window, signal)`` from :attr:`best` — scalars or per-factor tuples."""
        return self.params_from_best(self.best)

    @staticmethod
    def params_from_best(best: dict) -> tuple:
        """Extract ``(window, signal)`` from an optimize ``best`` row.

        Single-factor dicts use ``window`` / ``signal`` keys.
        Multi-factor dicts use ``window_0``, ``signal_0``, …
        """
        if "window" in best:
            return int(best["window"]), float(best["signal"])
        n = sum(1 for k in best if k.startswith("window_"))
        if n == 0:
            raise ValueError("best params missing window/signal keys")
        return (
            tuple(int(best[f"window_{i}"]) for i in range(n)),
            tuple(float(best[f"signal_{i}"]) for i in range(n)),
        )

    def extract_plots(self) -> dict | None:
        """Serialize optuna visualizations as Plotly JSON dicts.

        Auto-detects single vs multi-factor from grid_df column names.
        Returns None if study is unavailable or contains no completed trials.
        """
        if self.study is None:
            return None
        import json
        import optuna.visualization as optuna_vis

        n_factors = sum(1 for c in self.grid_df.columns if c.startswith("window_"))
        is_multi = n_factors > 0

        plots = {}
        try:
            plots["optimization_history"] = json.loads(
                optuna_vis.plot_optimization_history(self.study).to_json()
            )
        except Exception:
            pass
        try:
            plots["param_importances"] = json.loads(
                optuna_vis.plot_param_importances(self.study).to_json()
            )
        except Exception:
            pass

        if not is_multi:
            try:
                plots["contour"] = json.loads(
                    optuna_vis.plot_contour(self.study).to_json()
                )
            except Exception:
                pass
        else:
            try:
                plots["parallel_coordinate"] = json.loads(
                    optuna_vis.plot_parallel_coordinate(self.study).to_json()
                )
            except Exception:
                pass
            for i in range(n_factors):
                try:
                    plots[f"contour_factor_{i}"] = json.loads(
                        optuna_vis.plot_contour(
                            self.study, params=[f"window_{i}", f"signal_{i}"]
                        ).to_json()
                    )
                except Exception:
                    pass
        return plots or None


class SearchSpace:
    """Named categorical axes the search walks, plus the window spec for Objective."""

    def __init__(self, mapping: dict, window_spec, n_factors: int) -> None:
        self.mapping = mapping
        self.window_spec = window_spec
        self.n_factors = n_factors

    @classmethod
    def single(cls, window_values, signal_values) -> "SearchSpace":
        return cls(
            {"window": list(window_values), "signal": list(signal_values)},
            window_values,
            1,
        )

    @classmethod
    def multi(cls, window_ranges, signal_ranges) -> "SearchSpace":
        n_factors = len(window_ranges)
        if len(signal_ranges) != n_factors:
            raise ValueError(
                f"window_ranges has {n_factors} entries but "
                f"signal_ranges has {len(signal_ranges)}"
            )
        mapping = {}
        for i, (windows, signals) in enumerate(zip(window_ranges, signal_ranges)):
            mapping[f"window_{i}"] = list(windows)
            mapping[f"signal_{i}"] = list(signals)
        return cls(mapping, window_ranges, n_factors)

    @property
    def total(self) -> int:
        if self.n_factors == 1:
            return len(self.mapping["window"]) * len(self.mapping["signal"])
        return math.prod(
            len(self.mapping[f"window_{i}"]) * len(self.mapping[f"signal_{i}"])
            for i in range(self.n_factors)
        )

    @property
    def keys(self) -> list:
        return list(self.mapping)

    def distributions(self) -> dict:
        return {k: CategoricalDistribution(v) for k, v in self.mapping.items()}

    def windows_signals(self, params: dict) -> tuple[tuple, tuple]:
        if "window" in params:
            return (params["window"],), (params["signal"],)
        return (
            tuple(params[f"window_{i}"] for i in range(self.n_factors)),
            tuple(params[f"signal_{i}"] for i in range(self.n_factors)),
        )


class SearchStrategy(ABC):
    """Proposes parameter sets, evaluates them, records each as a COMPLETE trial."""

    @abstractmethod
    def search(self, objective, space: SearchSpace, n_trials, callbacks) -> optuna.Study:
        """Run *n_trials* evaluations and return the populated study."""

    @abstractmethod
    def log_start(self, space: SearchSpace, n_trials: int) -> None:
        """One INFO line naming this search, before the loop."""

    def evaluate(self, objective, windows, signals) -> float:
        try:
            sharpe = objective(windows, signals)
            return sharpe if np.isfinite(sharpe) else float("-inf")
        except Exception:
            logger.warning("Optimization failed for windows=%s, signals=%s",
                           windows, signals, exc_info=True)
            return float("-inf")


class ExhaustiveSearch(SearchStrategy):
    """Every combination, product order, recorded with ``study.add_trial``."""

    def log_start(self, space: SearchSpace, n_trials: int) -> None:
        if space.n_factors == 1:
            logger.info(
                "Exhaustive optimization: %d windows × %d signals = %d trials",
                len(space.mapping["window"]), len(space.mapping["signal"]),
                space.total,
            )
            return
        logger.info(
            "Exhaustive multi-factor optimization: %d factors, %d trials",
            space.n_factors, space.total,
        )

    def search(self, objective, space: SearchSpace, n_trials, callbacks) -> optuna.Study:
        distributions = space.distributions()
        study = optuna.create_study(direction="maximize")
        cbs = callbacks or []
        for combo in itertools.product(*(space.mapping[k] for k in space.keys)):
            params = dict(zip(space.keys, combo))
            windows, signals = space.windows_signals(params)
            value = self.evaluate(objective, windows, signals)
            study.add_trial(create_trial(
                params=params, distributions=distributions, value=value,
            ))
            frozen = study.get_trials(deepcopy=False)[-1]
            for cb in cbs:
                cb(study, frozen)
        return study


class BayesianSearch(SearchStrategy):
    """``TPESampler`` through ``study.optimize``."""

    def __init__(self) -> None:
        self._objective = None
        self._space: SearchSpace | None = None

    def log_start(self, space: SearchSpace, n_trials: int) -> None:
        if space.n_factors == 1:
            logger.info(
                "Bayesian optimization: %d space, %d trials (TPE)",
                space.total, n_trials,
            )
            return
        logger.info(
            "Bayesian multi-factor optimization: "
            "%d factors, %d space, %d trials (TPE)",
            space.n_factors, space.total, n_trials,
        )

    def search(self, objective, space: SearchSpace, n_trials, callbacks) -> optuna.Study:
        self._objective = objective
        self._space = space
        study = optuna.create_study(
            direction="maximize", sampler=TPESampler(seed=OPTUNA_SEED),
        )
        study.optimize(
            self.suggest_and_evaluate,
            n_trials=n_trials,
            callbacks=callbacks or [],
        )
        return study

    def suggest_and_evaluate(self, trial) -> float:
        params = {
            k: trial.suggest_categorical(k, self._space.mapping[k])
            for k in self._space.keys
        }
        windows, signals = self._space.windows_signals(params)
        return self.evaluate(self._objective, windows, signals)


class ParametersOptimization:

    def __init__(self, data, config, *, fee_bps=None):
        self.data = data
        self.config = config
        self.fee_bps = fee_bps

    def optimize(self, window_values, signal_values, *, n_trials=None,
                 callbacks=None):
        """Optimize window × signal.

        Exhaustive (Cartesian product) when *n_trials* covers the full space,
        Bayesian (TPE) otherwise.
        """
        return self._run(
            SearchSpace.single(window_values, signal_values),
            n_trials, callbacks,
        )

    def optimize_multi(self, window_ranges, signal_ranges, *, n_trials=None,
                       callbacks=None):
        """Multi-factor optimization over N-dimensional parameter space."""
        return self._run(
            SearchSpace.multi(window_ranges, signal_ranges),
            n_trials, callbacks,
        )

    def run(self, window_values, signal_values, *, n_trials=None, callbacks=None):
        """Auto-dispatch to optimize() or optimize_multi() based on config substrategies."""
        if len(self.config.get_substrategies()) > 1:
            return self.optimize_multi(
                window_values, signal_values,
                n_trials=n_trials, callbacks=callbacks,
            )
        return self.optimize(
            window_values, signal_values,
            n_trials=n_trials, callbacks=callbacks,
        )

    def _run(self, space: SearchSpace, n_trials, callbacks) -> OptimizeResult:
        search, n_trials = self._select_search(space.total, n_trials)
        search.log_start(space, n_trials)
        objective = Objective.for_config(
            self.data, self.config, space.window_spec, fee_bps=self.fee_bps,
        )
        study = search.search(objective, space, n_trials, callbacks)
        rows = self._rows_from_study(study, space.keys)
        logger.info("Optimization complete: %d trials evaluated", len(rows))
        return self._build_result(pd.DataFrame(rows), study)

    @staticmethod
    def _select_search(total, n_trials) -> tuple[SearchStrategy, int]:
        if n_trials is None:
            n_trials = min(total, OPTUNA_MAX_TRIALS)
        if n_trials >= total:
            return ExhaustiveSearch(), total
        return BayesianSearch(), n_trials

    @staticmethod
    def _rows_from_study(study, keys) -> list[dict]:
        rows = []
        for trial in study.get_trials(deepcopy=False):
            if trial.state != optuna.trial.TrialState.COMPLETE:
                continue
            sharpe = trial.value if trial.value > float("-inf") else np.nan
            row = {k: trial.params[k] for k in keys}
            row["sharpe"] = sharpe
            rows.append(row)
        return rows

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
