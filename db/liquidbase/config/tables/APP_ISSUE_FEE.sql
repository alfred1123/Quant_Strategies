-- Taker and maker fee in basis points, one row per broker and issue type.
-- A Bybit future is one rate: every perpetual on that exchange shares the row
-- whose ISSUE_TYPE is 'future'.
CREATE TABLE CONFIG.APP_ISSUE_FEE (
    APP_ISSUE_FEE_ID INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    APP_ID           INTEGER NOT NULL,
    ISSUE_TYPE       TEXT NOT NULL,
    MAKER_BPS        NUMERIC NOT NULL,
    TAKER_BPS        NUMERIC NOT NULL,
    USER_ID          TEXT,
    UPDATED_AT       TIMESTAMPTZ,
    UNIQUE (APP_ID, ISSUE_TYPE)
);
