-- BT.STRATEGY — soft-versioned strategy definitions.
--
-- One logical strategy = one STRATEGY_ID (UUID). Editing a strategy bumps
-- STRATEGY_VID and flips the prior row's IS_CURRENT_IND from 'Y' to 'N'.
-- CONFIG_JSON is the canonical OptimizeRequest payload (factors, ranges,
-- conjunction, ticker, trading_period, …) — single source of truth for
-- "what this backtest is".
--
-- BT.QUEUE rows reference (STRATEGY_ID, STRATEGY_VID); deleting a strategy
-- version is forbidden while any non-terminal queue row exists.
CREATE TABLE BT.STRATEGY (
    STRATEGY_ID    UUID NOT NULL,
    STRATEGY_VID   INTEGER NOT NULL,
    STRATEGY_NM    TEXT,
    CONFIG_JSON    JSONB NOT NULL,
    IS_CURRENT_IND CHAR(1) NOT NULL,
    USER_ID        TEXT NOT NULL,
    CREATED_AT     TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (STRATEGY_ID, STRATEGY_VID)
);
