-- BT.RESULT — slim payload bag for a completed backtest.
--
-- Inserted exactly once per COMPLETED queue submission. RESULT_ID is a
-- client-generated UUID (worker) supplied to BT.SP_INS_RESULT — not DB identity.
-- QUEUE_ID links to BT.QUEUE; strategy info and USER_ID join via QUEUE.
--
-- Key metrics are shredded from PAYLOAD_JSON into dedicated columns for
-- fast promotion comparison and Promotion tab queries. The full payload
-- (equity curves, trade log, CSV) stays in PAYLOAD_JSON.
--
-- No FK constraint on QUEUE_ID (BT.QUEUE PK is composite (QUEUE_ID,
-- QUEUE_VID); the result is associated with the submission, not a single
-- transition). Index covers the lookup.
CREATE TABLE BT.RESULT (
    RESULT_ID        UUID PRIMARY KEY,
    QUEUE_ID         UUID NOT NULL,
    PAYLOAD_JSON     JSONB NOT NULL,
    TOTAL_RETURN     NUMERIC,
    ANNUALIZED_RETURN NUMERIC,
    SHARPE_RATIO     NUMERIC,
    MAX_DRAWDOWN     NUMERIC,
    CALMAR_RATIO     NUMERIC,
    CREATED_AT       TIMESTAMPTZ NOT NULL
);

CREATE INDEX IX_RESULT_QUEUE ON BT.RESULT (QUEUE_ID);
