-- BT.QUEUE — soft-versioned state log for backtest jobs.
--
-- One submission of a strategy ⇒ one stable QUEUE_ID (UUID v7 from caller).
-- Each lifecycle transition (QUEUED → RUNNING → terminal) inserts a NEW row
-- with the same QUEUE_ID and the next QUEUE_VID, then flips the prior row's
-- IS_CURRENT_IND from 'Y' to 'N' (per AGENTS.md: no UPDATED_AT bump on flips —
-- there is no UPDATED_AT here at all, see "in-memory progress" below).
--
-- A retry / re-run of the same strategy ⇒ a NEW QUEUE_ID with QUEUE_VID=1.
-- Strategy versioning (BT.STRATEGY.STRATEGY_VID) tracks definition changes;
-- queue versioning (QUEUE_VID) tracks state transitions. The two are
-- independent: same (STRATEGY_ID, STRATEGY_VID) can be queued many times.
--
-- Progress is NOT stored here. The coordinator keeps trial counts in-memory
-- and streams them to clients over SSE; cancellation is delivered via OS
-- signal, not a DB poll. Keeps the row count bounded (~3 rows per job: QUEUED,
-- RUNNING, terminal) regardless of trial count.
--
-- ERROR_TEXT is plain text on the FAILED row.
-- Result payloads live in BT.RESULT and reference back via BT.RESULT.QUEUE_ID
-- (no RESULT_ID column on the queue row — caller does not have RESULT_ID at
-- the moment it inserts the COMPLETED transition).
CREATE TABLE BT.QUEUE (
    QUEUE_ID          UUID NOT NULL,
    QUEUE_VID         INTEGER NOT NULL,
    STRATEGY_ID       UUID NOT NULL,
    STRATEGY_VID      INTEGER NOT NULL,
    TRANSACT_FROM_TS TIMESTAMPTZ NOT NULL,
    TRANSACT_TO_TS   TIMESTAMPTZ NOT NULL,  -- 9999-12-31 when active
    QUEUE_STATUS_ID   INTEGER NOT NULL,
    PRIORITY          INTEGER NOT NULL,
    ERROR_TEXT        TEXT,
    USER_ID           TEXT NOT NULL,
    CREATED_AT        TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (QUEUE_ID, QUEUE_VID)
);

-- "Show me my latest queue submissions" — UI history list per user.
CREATE INDEX IX_QUEUE_USER_CURRENT
    ON BT.QUEUE (USER_ID, CREATED_AT DESC)
    WHERE TRANSACT_TO_TS = TIMESTAMPTZ '9999-12-31 00:00:00+00';

-- Worker dequeue path: find next QUEUED row across all jobs.
CREATE INDEX IX_QUEUE_STATUS_CURRENT
    ON BT.QUEUE (QUEUE_STATUS_ID, PRIORITY, CREATED_AT)
    WHERE TRANSACT_TO_TS = TIMESTAMPTZ '9999-12-31 00:00:00+00';

-- Strategy → all its queue submissions (for "show runs of this strategy").
CREATE INDEX IX_QUEUE_STRATEGY
    ON BT.QUEUE (STRATEGY_ID, STRATEGY_VID, CREATED_AT DESC);
