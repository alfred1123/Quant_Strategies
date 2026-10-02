-- TRADE.INTENT — one append-only row per deployment per apply pass.
--
-- What the strategy asked for, written before the order. TARGET_QTY is the
-- signed target position (SIGNAL_VALUE × QTY), not a delta. A later correction
-- is a new row. Joins its EXECUTION_EVENT rows on (DEPLOYMENT_ID, TRANSACT_AT).
-- Dry run writes nothing. Decision #90.
CREATE TABLE TRADE.INTENT (
    INTENT_ID        UUID NOT NULL,
    DEPLOYMENT_ID    UUID NOT NULL,
    DEPLOYMENT_VID   INTEGER NOT NULL,
    TM_INTERVAL_ID   INTEGER NOT NULL,
    BAR_TIMESTAMP    TIMESTAMPTZ NOT NULL,
    BAR_SOURCE       TEXT NOT NULL,
    SIGNAL_VALUE     NUMERIC NOT NULL,
    TARGET_QTY       NUMERIC NOT NULL,
    TRANSACT_AT      TIMESTAMPTZ NOT NULL,
    USER_ID          TEXT NOT NULL,
    CREATED_AT       TIMESTAMPTZ NOT NULL,

    PRIMARY KEY (INTENT_ID)
);

CREATE INDEX IX_INTENT_DEPLOYMENT_TS
    ON TRADE.INTENT (DEPLOYMENT_ID, TRANSACT_AT DESC);
