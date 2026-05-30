-- TRADE.EXECUTION_EVENT — append-only execution diary per deployment.
--
-- Records order submit attempts, rejects, and errors (e.g. min notional). Broker-
-- confirmed fills live in TRADE.TRANSACTION — not here.
--
-- UI execution panel (Phase 1.8) reads from this table; reconcile uses
-- TRADE.TRANSACTION.
CREATE TABLE TRADE.EXECUTION_EVENT (
    EXECUTION_EVENT_ID  UUID NOT NULL,
    DEPLOYMENT_ID       UUID NOT NULL,
    DEPLOYMENT_VID      INTEGER NOT NULL,
    SIGNAL_VALUE        NUMERIC,
    BUY_SELL_CD         TEXT NOT NULL,
    QUANTITY            NUMERIC,
    VENDOR_ORDER_ID     TEXT,
    IS_SUCCESS_IND      CHAR(1) NOT NULL,
    USER_ID             TEXT NOT NULL,
    CREATED_AT          TIMESTAMPTZ NOT NULL,

    PRIMARY KEY (EXECUTION_EVENT_ID)
);

CREATE INDEX IX_EXECUTION_EVENT_DEPLOYMENT_TS
    ON TRADE.EXECUTION_EVENT (DEPLOYMENT_ID, CREATED_AT DESC);
