-- TRADE.EXECUTION_EVENT — append-only execution diary per deployment.
--
-- Records order submit attempts, rejects, and errors (e.g. min notional). Broker-
-- confirmed fills live in TRADE.TRANSACTION — not here.
--
-- TRANSACT_AT = when the apply tick occurred (diary). CREATED_AT = audit insert.
-- Scheduler state lives in TRADE.DEPLOYMENT_SCHEDULE_STATUS — not this table.
--
-- SIGNAL_VALUE and POSITION_QTY are the two inputs to the decision this row
-- records: intended_side() compares the signal against the position the broker
-- reported, and answers HOLD when they already agree. POSITION_QTY is signed —
-- negative is short — and is the book *before* this attempt. Without it a HOLD
-- is indistinguishable from a missed tick, and on a scheduled apply nobody sees
-- the ApplyReport that used to be the only place the number appeared.
--
-- UI execution panel (Phase 1.8) reads from this table; reconcile uses
-- TRADE.TRANSACTION.
CREATE TABLE TRADE.EXECUTION_EVENT (
    EXECUTION_EVENT_ID  UUID NOT NULL,
    DEPLOYMENT_ID       UUID NOT NULL,
    DEPLOYMENT_VID      INTEGER NOT NULL,
    SIGNAL_VALUE        NUMERIC,
    POSITION_QTY        NUMERIC,
    BUY_SELL_CD         TEXT NOT NULL,
    QUANTITY            NUMERIC,
    VENDOR_ORDER_ID     TEXT,
    IS_SUCCESS_IND      CHAR(1) NOT NULL,
    TRANSACT_AT         TIMESTAMPTZ NOT NULL,
    USER_ID             TEXT NOT NULL,
    CREATED_AT          TIMESTAMPTZ NOT NULL,

    PRIMARY KEY (EXECUTION_EVENT_ID)
);

CREATE INDEX IX_EXECUTION_EVENT_DEPLOYMENT_TS
    ON TRADE.EXECUTION_EVENT (DEPLOYMENT_ID, CREATED_AT DESC);
