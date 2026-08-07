-- Normalized OHLCV bars for live signal computation (Phase 1.9).
-- Immutable facts — no soft-versioning. PK = natural bar key.
--
-- SOURCE_APP_ID is part of the key, not payload: one INTERNAL_CUSIP is traded on
-- several venues (decision #21 — btcusdt.crypto covers Bybit and Binance), and
-- their prints differ. Keying without it lets whichever venue writes a timestamp
-- first own it, so a window silently blends venues and a backtest over it is not
-- reproducible. A paid backfill provider is likewise just another SOURCE_APP_ID
-- rather than a collision. Every read must scope to one source.
CREATE TABLE MARKET_DATA.PRICE_BAR (
    INTERNAL_CUSIP   TEXT          NOT NULL,
    TM_INTERVAL_ID   INTEGER       NOT NULL,
    BAR_TIMESTAMP    TIMESTAMPTZ   NOT NULL,
    OPEN_PX          DECIMAL       NOT NULL,
    HIGH_PX          DECIMAL       NOT NULL,
    LOW_PX           DECIMAL       NOT NULL,
    CLOSE_PX         DECIMAL       NOT NULL,
    VOLUME           DECIMAL       NOT NULL,
    SOURCE_APP_ID    INTEGER       NOT NULL,
    USER_ID          TEXT          NOT NULL,
    CREATED_AT       TIMESTAMPTZ   NOT NULL,

    PRIMARY KEY (INTERNAL_CUSIP, TM_INTERVAL_ID, SOURCE_APP_ID, BAR_TIMESTAMP)
);

CREATE INDEX IX_PRICE_BAR_LATEST
    ON MARKET_DATA.PRICE_BAR (INTERNAL_CUSIP, TM_INTERVAL_ID, SOURCE_APP_ID, BAR_TIMESTAMP DESC)
    INCLUDE (CLOSE_PX);
