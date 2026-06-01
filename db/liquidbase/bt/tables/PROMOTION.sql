-- BT.PROMOTION — append-only log of promotion decisions for completed backtests.
--
-- One row per completed backtest, persisted by the worker immediately after
-- the promote/demote/keep/reject decision and before the COMPLETED queue
-- transition. Powers the Promotion tab UI.
--
-- Metric values (Sharpe, Calmar, etc.) live in BT.RESULT.PAYLOAD_JSON —
-- the UI derives the decisive metric by joining both payloads (candidate
-- via QUEUE_ID, best via COMPARED_VID's queue) and walking
-- REFDATA.PROMOTION_METRIC in priority order.
--
-- GATE_RESULTS is a point-in-time snapshot because REFDATA thresholds
-- may change after the decision was made.
CREATE TABLE BT.PROMOTION (
    PROMOTION_ID    UUID PRIMARY KEY,
    QUEUE_ID        UUID NOT NULL,
    STRATEGY_ID     UUID NOT NULL,
    STRATEGY_VID    INTEGER NOT NULL,
    OUTCOME         TEXT NOT NULL,       -- PROMOTED | KEPT | DEMOTED | REJECTED
    COMPARED_VID    INTEGER,             -- best VID compared against (NULL if no baseline)
    GATE_RESULTS    JSONB,               -- snapshot: [{name, passed, value, threshold}]
    USER_ID         TEXT NOT NULL,
    CREATED_AT      TIMESTAMPTZ NOT NULL
);

CREATE INDEX IX_PROMOTION_QUEUE ON BT.PROMOTION (QUEUE_ID);
CREATE INDEX IX_PROMOTION_STRATEGY ON BT.PROMOTION (STRATEGY_ID, STRATEGY_VID);
