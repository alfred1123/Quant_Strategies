-- One policy row for the parameter search: how many distinct cells to score,
-- the sampler seed, how many proposals may be spent chasing that budget,
-- and what to do when the grid is larger than the budget.
CREATE TABLE CONFIG.BACKTEST_SEARCH (
    BACKTEST_SEARCH_ID   INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    TRIAL_BUDGET         INTEGER NOT NULL,
    SEED                 INTEGER NOT NULL,
    MAX_ATTEMPTS_FACTOR  INTEGER NOT NULL,
    OVER_BUDGET_MODE     TEXT NOT NULL,
    USER_ID              TEXT,
    UPDATED_AT           TIMESTAMPTZ
);
