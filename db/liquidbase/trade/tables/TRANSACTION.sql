-- TRADE.TRANSACTION — append-only broker-confirmed fills per deployment.
--
-- Structured trade economics (qty, price, fees). Order submit errors and
-- pre-fill events live in TRADE.EXECUTION_EVENT.
--
-- FEE_AMT is the raw broker cost. FEE_CCY_CD is the coin that cost was
-- charged in. TRANS_CCY_CD is the product quote, not the fee coin. A row
-- written before FEE_CCY_CD existed has a null fee currency.
CREATE TABLE TRADE.TRANSACTION (
    TRANSACTION_ID      UUID NOT NULL,
    DEPLOYMENT_ID       UUID NOT NULL,
    APP_ID              INTEGER NOT NULL,
    ORDER_STATE_ID      INTEGER,
    TRANS_STATE_ID      INTEGER,
    INTERNAL_CUSIP      TEXT NOT NULL,
    VENDOR_SYMBOL       TEXT,
    BUY_SELL_CD         TEXT NOT NULL,
    TRANS_CCY_CD        TEXT NOT NULL,
    QUANTITY            NUMERIC,
    PRICE               NUMERIC,
    NOTIONAL_AMT        NUMERIC,
    FEE_AMT             NUMERIC,
    FEE_CCY_CD          TEXT,
    VENDOR_ORDER_ID     TEXT,
    USER_ID             TEXT NOT NULL,
    CREATED_AT          TIMESTAMPTZ NOT NULL,

    PRIMARY KEY (TRANSACTION_ID)
);

CREATE INDEX IX_TRANSACTION_DEPLOYMENT_TS
    ON TRADE.TRANSACTION (DEPLOYMENT_ID, CREATED_AT DESC);

CREATE INDEX IX_TRANSACTION_VENDOR_ORDER
    ON TRADE.TRANSACTION (APP_ID, VENDOR_ORDER_ID)
    WHERE VENDOR_ORDER_ID IS NOT NULL;
