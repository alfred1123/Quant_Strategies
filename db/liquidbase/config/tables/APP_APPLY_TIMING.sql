-- Scheduled-apply delay per broker and cadence (broker API / ops tuning).
--
-- Session calendar (timezone, market hours) lives in REFDATA.MARKET_CALENDAR.
-- EXECUTE_OFFSET — lead time before bar close (trade while the candle is still open).
CREATE TABLE CONFIG.APP_APPLY_TIMING (
    APP_APPLY_TIMING_ID  INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    APP_ID               INTEGER NOT NULL,
    TM_INTERVAL_ID       INTEGER NOT NULL,
    EXECUTE_OFFSET       INTERVAL NOT NULL,
    USER_ID              TEXT,
    UPDATED_AT           TIMESTAMPTZ,
    UNIQUE (APP_ID, TM_INTERVAL_ID)
);
