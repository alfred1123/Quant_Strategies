-- A standing request to keep one provider series, with no backtest behind it.
--
-- The key the Data tab joins on is PROVIDER_SUBSCR_ID. MARKET_DATA.API_REQUEST stores
-- that id on the window it fetched. The series columns are how a second
-- subscribe finds the same id. INST.PRODUCT_XREF stays the vendor symbol.
--
-- No USER_ID. The procedure logs the caller, the same way BAR_SUBSCRIPTION
-- does. One open row per series. Disabling it stops the fetch for everyone.
CREATE TABLE MARKET_DATA.PROVIDER_SUBSCR (
    PROVIDER_SUBSCR_ID    UUID          NOT NULL,
    PROVIDER_SUBSCR_VID   INTEGER       NOT NULL,
    INTERNAL_CUSIP        TEXT          NOT NULL,
    APP_ID                INTEGER       NOT NULL,
    APP_METRIC_ID         INTEGER       NOT NULL,
    TM_INTERVAL_ID        INTEGER       NOT NULL,
    IS_ENABLED_IND        CHAR(1)       NOT NULL,
    -- How far back the series is wanted. NULL = forward only.
    BACKFILL_FROM_TS      TIMESTAMPTZ,
    TRANSACT_FROM_TS      TIMESTAMPTZ   NOT NULL,
    TRANSACT_TO_TS        TIMESTAMPTZ   NOT NULL,
    CREATED_AT            TIMESTAMPTZ   NOT NULL,

    PRIMARY KEY (PROVIDER_SUBSCR_ID, PROVIDER_SUBSCR_VID)
);

-- Current row for one id. The list join and a get-by-id both use it.
CREATE UNIQUE INDEX UQ_PROVIDER_SUBSCR_ID_OPEN
    ON MARKET_DATA.PROVIDER_SUBSCR (PROVIDER_SUBSCR_ID)
    WHERE TRANSACT_TO_TS = TIMESTAMPTZ '9999-12-31 00:00:00+00';

-- One open subscription per series, so a second subscribe reuses the id.
CREATE UNIQUE INDEX UQ_PROVIDER_SUBSCR_OPEN
    ON MARKET_DATA.PROVIDER_SUBSCR (APP_METRIC_ID, TM_INTERVAL_ID, INTERNAL_CUSIP)
    WHERE TRANSACT_TO_TS = TIMESTAMPTZ '9999-12-31 00:00:00+00';
