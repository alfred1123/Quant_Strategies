'''
Parameter optimization for single-factor and multi-factor strategies.

ExhaustiveSearch walks the Cartesian product when the grid fits in the
trial budget and records each cell into an optuna study (for plots).
A larger grid is handled by CONFIG.BACKTEST_SEARCH.OVER_BUDGET_MODE:
TPE over distinct cells, a seeded random sample of distinct cells, or
a refusal. A repeated proposal is told back to the sampler and is not
scored again.
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

TPE_DISTINCT = "TPE_DISTINCT"
RANDOM_DISTINCT = "RANDOM_DISTINCT"
REJECT = "REJECT"
OVER_BUDGET_MODES = (TPE_DISTINCT, RANDOM_DISTINCT, REJECT)

_REPEAT = "repeat"
_EXHAUSTIVE = "exhaustive"
_TPE_SAMPLE = "TPE sample"
_RANDOM_SAMPLE = "random sample"


@dataclass(frozen=True)
class SearchPolicy:
    """Budget, seed, attempt cap, and over-budget mode from CONFIG.BACKTEST_SEARCH."""

    trial_budget: int
    seed: int
    max_attempts_factor: int
    over_budget_mode: str

    def __post_init__(self) -> None:
        if self.trial_budget < 1:
            raise ValueError(f"trial_budget must be >= 1, got {self.trial_budget}")
        if self.max_attempts_factor < 1:
            raise ValueError(
                f"max_attempts_factor must be >= 1, got {self.max_attempts_factor}"
            )

    @classmethod
    def from_row(cls, row: dict) -> "SearchPolicy":
        return cls(
            trial_budget=int(row["trial_budget"]),
            seed=int(row["seed"]),
            max_attempts_factor=int(row["max_attempts_factor"]),
            over_budget_mode=str(row["over_budget_mode"]),
        )

    @property
    def max_attempts(self) -> int:
        return self.trial_budget * self.max_attempts_factor


@dataclass(frozen=True)
class SearchReport:
    """What the search actually did, after the loop stops."""

    search: str
    grid_size: int
    distinct_cells: int
    attempts: int


class OverBudgetGrid(Exception):
    """OVER_BUDGET_MODE is REJECT and the grid is larger than the budget."""

    def __init__(self, grid_size: int, trial_budget: int) -> None:
        self.grid_size = grid_size
        self.trial_budget = trial_budget
        super().__init__(
            f"grid of {grid_size} cells exceeds the trial budget of {trial_budget}"
        )


@dataclass
class OptimizeResult:
    """Result returned by ParametersOptimization.optimize() and optimize_multi()."""

    grid_df: pd.DataFrame  # One row per distinct cell — NaN preserved, for CSV/heatmap
    best: dict             # Best params by Sharpe (NaN → None)
    top10: list            # Top 10 by Sharpe descending (NaN → None)
    grid: list             # All distinct rows (NaN → None)
    n_valid: int           # Distinct cells with finite Sharpe
    study: object          # optuna.Study — for visualization
    search: str            # "exhaustive", "TPE sample", or "random sample"
    grid_size: int         # Cells in the Cartesian product
    distinct_cells: int    # Cells scored
    attempts: int          # Proposals, including ones told back as repeats

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

    def cell_key(self, params: dict) -> tuple:
        """Identity of one cell. Every axis is in the key, in grid order."""
        return tuple(params[k] for k in self.keys)

    def distributions(self) -> dict:
        return {k: CategoricalDistribution(v) for k, v in self.mapping.items()}

    def windows_signals(self, params: dict) -> tuple[tuple, tuple]:
        if "window" in params:
            return (params["window"],), (params["signal"],)
        return (
            tuple(params[f"window_{i}"] for i in range(self.n_factors)),
            tuple(params[f"signal_{i}"] for i in range(self.n_factors)),
        )

    def combo_at(self, index: int) -> tuple:
        """The cell at a flat index. The last axis changes fastest, as ``product`` does."""
        axes = [self.mapping[k] for k in self.keys]
        coords = []
        for axis in reversed(axes):
            coords.append(axis[index % len(axis)])
            index //= len(axis)
        coords.reverse()
        return tuple(coords)


def _notify(study, callbacks) -> None:
    if not callbacks:
        return
    frozen = study.trials[-1]
    for cb in callbacks:
        cb(study, frozen)


class SearchStrategy(ABC):
    """Proposes parameter cells and records each scored cell as a COMPLETE trial."""

    @abstractmethod
    def search(self, objective, space: SearchSpace, callbacks) -> tuple:
        """Run the search and return ``(study, SearchReport)``."""

    @abstractmethod
    def log_start(self, space: SearchSpace, budget: int) -> None:
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

    def log_start(self, space: SearchSpace, budget: int) -> None:
        if space.n_factors == 1:
            logger.info(
                "Exhaustive optimization: %d windows × %d signals = %d cells",
                len(space.mapping["window"]), len(space.mapping["signal"]),
                space.total,
            )
            return
        logger.info(
            "Exhaustive multi-factor optimization: %d factors, %d cells",
            space.n_factors, space.total,
        )

    def search(self, objective, space: SearchSpace, callbacks) -> tuple:
        distributions = space.distributions()
        study = optuna.create_study(direction="maximize")
        for combo in itertools.product(*(space.mapping[k] for k in space.keys)):
            params = dict(zip(space.keys, combo))
            windows, signals = space.windows_signals(params)
            value = self.evaluate(objective, windows, signals)
            study.add_trial(create_trial(
                params=params, distributions=distributions, value=value,
            ))
            _notify(study, callbacks)
        report = SearchReport(
            search=_EXHAUSTIVE,
            grid_size=space.total,
            distinct_cells=space.total,
            attempts=space.total,
        )
        return study, report


class BayesianSearch(SearchStrategy):
    """TPE over distinct cells. A repeat is told its stored score and not re-scored."""

    def __init__(self, policy: SearchPolicy) -> None:
        self.policy = policy

    def log_start(self, space: SearchSpace, budget: int) -> None:
        if space.n_factors == 1:
            logger.info(
                "TPE sample: %d cells, budget %d, attempt cap %d",
                space.total, budget, self.policy.max_attempts,
            )
            return
        logger.info(
            "TPE sample: %d factors, %d cells, budget %d, attempt cap %d",
            space.n_factors, space.total, budget, self.policy.max_attempts,
        )

    def search(self, objective, space: SearchSpace, callbacks) -> tuple:
        study = optuna.create_study(
            direction="maximize",
            sampler=TPESampler(seed=self.policy.seed),
        )
        scored: dict[tuple, float] = {}
        attempts = 0
        budget = self.policy.trial_budget
        cap = self.policy.max_attempts
        while len(scored) < budget and attempts < cap and len(scored) < space.total:
            trial = study.ask()
            params = {
                k: trial.suggest_categorical(k, space.mapping[k])
                for k in space.keys
            }
            key = space.cell_key(params)
            attempts += 1
            if key in scored:
                trial.set_user_attr(_REPEAT, True)
                study.tell(trial, scored[key])
                _notify(study, callbacks)
                continue
            windows, signals = space.windows_signals(params)
            value = self.evaluate(objective, windows, signals)
            scored[key] = value
            study.tell(trial, value)
            _notify(study, callbacks)
        report = SearchReport(
            search=_TPE_SAMPLE,
            grid_size=space.total,
            distinct_cells=len(scored),
            attempts=attempts,
        )
        return study, report


class RandomDistinctSearch(SearchStrategy):
    """Seeded sample of distinct cells, drawn without replacement from the grid index."""

    def __init__(self, policy: SearchPolicy) -> None:
        self.policy = policy

    def log_start(self, space: SearchSpace, budget: int) -> None:
        logger.info(
            "Random sample: %d distinct cells of %d (seed %d)",
            budget, space.total, self.policy.seed,
        )

    def search(self, objective, space: SearchSpace, callbacks) -> tuple:
        budget = self.policy.trial_budget
        rng = np.random.default_rng(self.policy.seed)
        indices = rng.choice(space.total, size=budget, replace=False)
        distributions = space.distributions()
        study = optuna.create_study(direction="maximize")
        for index in indices:
            combo = space.combo_at(int(index))
            params = dict(zip(space.keys, combo))
            windows, signals = space.windows_signals(params)
            value = self.evaluate(objective, windows, signals)
            study.add_trial(create_trial(
                params=params, distributions=distributions, value=value,
            ))
            _notify(study, callbacks)
        report = SearchReport(
            search=_RANDOM_SAMPLE,
            grid_size=space.total,
            distinct_cells=budget,
            attempts=budget,
        )
        return study, report


class ParametersOptimization:

    def __init__(self, data, config, *, fee_bps=None, search: SearchPolicy):
        self.data = data
        self.config = config
        self.fee_bps = fee_bps
        self.search = search

    def optimize(self, window_values, signal_values, *, callbacks=None):
        """Optimize window × signal.

        Exhaustive when the trial budget covers the grid. Otherwise the
        policy's over-budget mode selects the search.
        """
        return self._run(
            SearchSpace.single(window_values, signal_values),
            callbacks,
        )

    def optimize_multi(self, window_ranges, signal_ranges, *, callbacks=None):
        """Multi-factor optimization over N-dimensional parameter space."""
        return self._run(
            SearchSpace.multi(window_ranges, signal_ranges),
            callbacks,
        )

    def run(self, window_values, signal_values, *, callbacks=None):
        """Auto-dispatch to optimize() or optimize_multi() based on config substrategies."""
        if len(self.config.get_substrategies()) > 1:
            return self.optimize_multi(
                window_values, signal_values, callbacks=callbacks,
            )
        return self.optimize(
            window_values, signal_values, callbacks=callbacks,
        )

    def _run(self, space: SearchSpace, callbacks) -> OptimizeResult:
        search = self._select_search(space.total)
        search.log_start(space, self.search.trial_budget)
        objective = Objective.for_config(
            self.data, self.config, space.window_spec, fee_bps=self.fee_bps,
        )
        study, report = search.search(objective, space, callbacks)
        rows = self._rows_from_study(study, space.keys)
        logger.info(
            "Optimization complete: %d distinct cells of %d (%s, %d attempts)",
            report.distinct_cells, report.grid_size, report.search, report.attempts,
        )
        return self._build_result(pd.DataFrame(rows), study, report)

    def _select_search(self, total: int) -> SearchStrategy:
        if total <= self.search.trial_budget:
            return ExhaustiveSearch()
        mode = self.search.over_budget_mode
        if mode == REJECT:
            raise OverBudgetGrid(total, self.search.trial_budget)
        if mode == TPE_DISTINCT:
            return BayesianSearch(self.search)
        if mode == RANDOM_DISTINCT:
            return RandomDistinctSearch(self.search)
        raise ValueError(
            f"CONFIG.BACKTEST_SEARCH OVER_BUDGET_MODE {mode!r} is not one of "
            + ", ".join(OVER_BUDGET_MODES)
        )

    @staticmethod
    def _rows_from_study(study, keys) -> list[dict]:
        rows = []
        for trial in study.get_trials(deepcopy=False):
            if trial.state != optuna.trial.TrialState.COMPLETE:
                continue
            if trial.user_attrs.get(_REPEAT):
                continue
            sharpe = trial.value if trial.value > float("-inf") else np.nan
            row = {k: trial.params[k] for k in keys}
            row["sharpe"] = sharpe
            rows.append(row)
        return rows

    @staticmethod
    def _build_result(df: pd.DataFrame, study, report: SearchReport) -> "OptimizeResult":
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
            search=report.search,
            grid_size=report.grid_size,
            distinct_cells=report.distinct_cells,
            attempts=report.attempts,
        )
