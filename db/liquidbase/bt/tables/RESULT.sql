-- BT.RESULT — slim payload bag for a completed backtest.
--
-- Inserted exactly once per COMPLETED queue submission. RESULT_ID is a
-- client-generated UUID (worker) supplied to BT.SP_INS_RESULT — not DB identity.
-- QUEUE_ID links to the originating submission; STRATEGY_ID + STRATEGY_VID
-- are denormalized at insert time for direct strategy-scoped metric lookups.
-- RESULT_VID + IS_CURRENT_IND soft-version within (STRATEGY_ID, STRATEGY_VID):
-- re-backtesting the same strategy VID bumps RESULT_VID and flips prior rows.
--
-- Key metrics are shredded from PAYLOAD_JSON into dedicated columns for
-- fast promotion comparison and catalog queries. The full payload
-- (equity curves, trade log, CSV) stays in PAYLOAD_JSON.
--
-- No FK constraint on QUEUE_ID (BT.QUEUE PK is composite (QUEUE_ID,
-- QUEUE_VID); the result is associated with the submission, not a single
-- transition). Indexes cover queue and strategy lookups.
CREATE TABLE BT.RESULT (
    RESULT_ID         UUID PRIMARY KEY,
    QUEUE_ID          UUID NOT NULL,
    STRATEGY_ID       UUID,
    STRATEGY_VID      INTEGER,
    RESULT_VID        INTEGER NOT NULL,
    IS_CURRENT_IND    CHAR(1) NOT NULL,
    PAYLOAD_JSON      JSONB NOT NULL,
    TOTAL_RETURN      NUMERIC,
    ANNUALIZED_RETURN NUMERIC,
    SHARPE_RATIO      NUMERIC,
    MAX_DRAWDOWN      NUMERIC,
    CALMAR_RATIO      NUMERIC,
    CREATED_AT        TIMESTAMPTZ NOT NULL
);

CREATE INDEX IX_RESULT_QUEUE ON BT.RESULT (QUEUE_ID);
CREATE INDEX IX_RESULT_STRATEGY ON BT.RESULT (STRATEGY_ID, STRATEGY_VID, CREATED_AT DESC);
CREATE INDEX IX_RESULT_STRATEGY_CURRENT ON BT.RESULT (STRATEGY_ID, STRATEGY_VID)
    WHERE IS_CURRENT_IND = 'Y';
