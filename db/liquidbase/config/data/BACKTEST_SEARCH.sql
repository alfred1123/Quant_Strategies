-- Default search: 10,000 distinct cells, seed 42, stop after 3× the budget
-- of proposals, TPE over cells that have not been scored yet.
-- OVER_BUDGET_MODE may also be RANDOM_DISTINCT or REJECT.
INSERT INTO CONFIG.BACKTEST_SEARCH (
    TRIAL_BUDGET,
    SEED,
    MAX_ATTEMPTS_FACTOR,
    OVER_BUDGET_MODE,
    USER_ID,
    UPDATED_AT
)
SELECT 10000,
       42,
       3,
       'TPE_DISTINCT',
       'system',
       NOW()
 WHERE NOT EXISTS (
       SELECT 1
         FROM CONFIG.BACKTEST_SEARCH
 );
