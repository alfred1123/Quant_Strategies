-- BT.RESULT — slim payload bag for a completed backtest.
--
-- Inserted exactly once per COMPLETED queue submission. QUEUE_ID is the
-- logical link back to BT.QUEUE (the soft-versioned state log) — strategy
-- info is reachable by joining BT.QUEUE on QUEUE_ID. PAYLOAD_JSON merges
-- the legacy METRICS_JSON + WALK_FORWARD_JSON + run metadata (run_at,
-- data_start, data_end, fee_bps, ticker, …) into one document; the API
-- shapes the response.
--
-- No FK constraint on QUEUE_ID (BT.QUEUE PK is composite (QUEUE_ID,
-- QUEUE_VID); the result is associated with the submission, not a single
-- transition). Index covers the lookup.
CREATE TABLE BT.RESULT (
    RESULT_ID    INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    QUEUE_ID     UUID NOT NULL,
    PAYLOAD_JSON JSONB NOT NULL,
    USER_ID      TEXT,
    CREATED_AT   TIMESTAMPTZ NOT NULL
);

CREATE INDEX IX_RESULT_QUEUE ON BT.RESULT (QUEUE_ID);
