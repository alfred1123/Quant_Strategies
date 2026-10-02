"""A search policy wide enough that the small grids in the suite stay exhaustive."""

from quant.strategy.optimizer import SearchPolicy

WIDE = SearchPolicy(
    trial_budget=10_000,
    seed=42,
    max_attempts_factor=3,
    over_budget_mode="TPE_DISTINCT",
)
