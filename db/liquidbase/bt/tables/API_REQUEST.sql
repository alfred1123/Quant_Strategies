-- One row per unique data subscription (symbol + source + interval).
-- Metadata only — payloads live in API_REQUEST_PAYLOAD.
CREATE TABLE BT.API_REQUEST (
    API_REQ_ID       UUID NOT NULL,
    API_REQ_VID      INTEGER NOT NULL,
    APP_ID           INTEGER,
    TM_INTERVAL_ID   INTEGER,
    SYMBOL           TEXT NOT NULL,
    FULL_RANGE_START TIMESTAMPTZ,          -- earliest date across all versions
    FULL_RANGE_END   TIMESTAMPTZ,          -- latest date across all versions
    IS_CURRENT_IND   CHAR(1),
    USER_ID          TEXT,
    CREATED_AT       TIMESTAMPTZ,
    PRIMARY KEY (API_REQ_ID, API_REQ_VID)
);
