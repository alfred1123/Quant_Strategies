-- Backtest queue priority labels. The API accepts NAME; PRIORITY is the
-- BT.QUEUE.PRIORITY integer the worker orders by (lower runs first).
CREATE TABLE REFDATA.QUEUE_PRIORITY (
    QUEUE_PRIORITY_ID  INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    NAME               TEXT NOT NULL UNIQUE,
    DISPLAY_NAME       TEXT,
    PRIORITY           INTEGER NOT NULL,
    DESCRIPTION        TEXT,
    USER_ID            TEXT,
    UPDATED_AT         TIMESTAMPTZ
);
