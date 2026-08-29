-- A standing request to keep one bar series warm, with no deployment behind it.
--
-- Bars could previously only be collected for an instrument some strategy was
-- already deployed against, so the one thing you could not do was collect prices
-- for a product while deciding whether to trade it — the backtest that informs
-- the decision needs history, and history only started once the decision was
-- made. A subscription is that missing second answer to "which instruments
-- matter"; the warmer unions it with the deployment-derived list.
--
-- The key is MARKET_DATA.PRICE_BAR's key minus BAR_TIMESTAMP. SOURCE_APP_ID
-- belongs in it for the same reason it belongs there (decision #47): a bar is a
-- fact from a venue, so btcusdt.crypto on Bybit and on Binance are two series
-- and subscribing to one is not subscribing to the other.
--
-- Deliberately NOT scoped to a user. A bar is a shared fact — one row per
-- (cusip, interval, venue, timestamp), visible to everyone — so a per-user
-- request row would model private ownership of something nobody owns, and buy
-- only a DISTINCT in the warmer's read. One row per series instead: whoever
-- captures it captures it for the platform. The cost is real and accepted —
-- disabling a subscription stops the capture for every user, not just the one
-- who asked — which is why the row and its history are visible to all of them.
--
-- No USER_ID, which is a deliberate exception to the audit convention every
-- other table follows, and the reason is that here it would be a second copy of
-- something already recorded. SP_INS_BAR_SUBSCRIPTION still takes IN_USER_ID
-- and passes it to CORE_ADMIN.CORE_INS_LOG_PROC, so who enabled, disabled or
-- retargeted a series is answerable from CORE_ADMIN.LOG_PROC against the version
-- window this table already stamps. Storing it on the row too would be a
-- duplicate free to disagree with the log. Nothing in the API or UI ever read
-- it, so it bought nothing on the read side either.
--
-- Soft-versioned like TRADE.DEPLOYMENT: enabling, disabling and retargeting are
-- edits to a mutable entity, and the version history doubles as a record of
-- which series the platform was capturing when — part of reproducing a backtest.
-- No UPDATED_AT, per the convention that IS_CURRENT_IND-style flips insert a new
-- row rather than update one.
CREATE TABLE MARKET_DATA.BAR_SUBSCRIPTION (
    BAR_SUBSCRIPTION_ID   UUID          NOT NULL,
    BAR_SUBSCRIPTION_VID  INTEGER       NOT NULL,
    INTERNAL_CUSIP        TEXT          NOT NULL,
    TM_INTERVAL_ID        INTEGER       NOT NULL,
    SOURCE_APP_ID         INTEGER       NOT NULL,
    IS_ENABLED_IND        CHAR(1)       NOT NULL,
    -- Intent, not progress: how far back history is wanted, so the UI can show a
    -- target and offer to fill toward it. NULL = forward only. A column tracking
    -- progress would imply a background crawler nothing here runs — backfill
    -- stays an explicit, reported operation.
    BACKFILL_FROM_TS      TIMESTAMPTZ,
    TRANSACT_FROM_TS      TIMESTAMPTZ   NOT NULL,
    TRANSACT_TO_TS        TIMESTAMPTZ   NOT NULL,  -- 9999-12-31 when active
    CREATED_AT            TIMESTAMPTZ   NOT NULL,

    PRIMARY KEY (BAR_SUBSCRIPTION_ID, BAR_SUBSCRIPTION_VID)
);

-- One live subscription per series, which is what makes the warmer's read a
-- plain scan rather than a DISTINCT: the index is the uniqueness. It also stops
-- a double-submit leaving two open rows nobody can tell apart, where disabling
-- one reads as a no-op because the other still keeps the series warm.
CREATE UNIQUE INDEX UQ_BAR_SUBSCRIPTION_OPEN
    ON MARKET_DATA.BAR_SUBSCRIPTION (TM_INTERVAL_ID, INTERNAL_CUSIP, SOURCE_APP_ID)
    WHERE TRANSACT_TO_TS = TIMESTAMPTZ '9999-12-31 00:00:00+00';

-- The list read: every open row, enabled or not, ordered for display.
CREATE INDEX IX_BAR_SUBSCRIPTION_OPEN
    ON MARKET_DATA.BAR_SUBSCRIPTION (INTERNAL_CUSIP, TM_INTERVAL_ID, SOURCE_APP_ID)
    WHERE TRANSACT_TO_TS = TIMESTAMPTZ '9999-12-31 00:00:00+00';
