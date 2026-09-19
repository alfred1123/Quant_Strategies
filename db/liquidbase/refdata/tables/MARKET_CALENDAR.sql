-- Listing-venue trading calendar — keyed by INST.PRODUCT.EXCHANGE, not broker (APP).
--
-- LISTING_EXCHANGE — listing/clearing venue on the product. Empty string is the
--   default row for instruments with no exchange (e.g. .crypto spot): UTC 24/7,
--   ccxt midnight daily boundaries. HKEX, NYSE, etc. get their own rows.
--
-- BAR_TIMEZONE — IANA zone for MARKET_OPEN_TIME / MARKET_CLOSE_TIME (wall clock).
-- MARKET_OPEN_TIME / MARKET_CLOSE_TIME — regular session in BAR_TIMEZONE.
--   NULL on both = continuous market (24/7). Holidays are not modeled here.
CREATE TABLE REFDATA.MARKET_CALENDAR (
    MARKET_CALENDAR_ID   INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    LISTING_EXCHANGE     TEXT NOT NULL UNIQUE,
    BAR_TIMEZONE         TEXT NOT NULL,
    MARKET_OPEN_TIME     TIME,
    MARKET_CLOSE_TIME    TIME,
    USER_ID              TEXT,
    UPDATED_AT           TIMESTAMPTZ
);
