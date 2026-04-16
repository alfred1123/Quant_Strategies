-- One row per unique data subscription (product group + source + interval).
-- Metadata only — payloads live in API_REQUEST_PAYLOAD.
-- Temporal versioning: TRANSACT_TO_TS = '9999-12-31' for the active row.
CREATE TABLE BT.API_REQUEST (
    API_REQ_ID         UUID NOT NULL,
    API_REQ_VID        INTEGER NOT NULL,
    APP_ID             INTEGER,
    APP_METRIC_ID      INTEGER,
    TM_INTERVAL_ID     INTEGER,
    PRODUCT_GROUP_ID   INTEGER,
    FULL_RANGE_START   TIMESTAMPTZ,          -- earliest date across all versions
    FULL_RANGE_END     TIMESTAMPTZ,          -- latest date across all versions
    TRANSACT_FROM_TS   TIMESTAMPTZ,          -- version effective from
    TRANSACT_TO_TS     TIMESTAMPTZ,          -- 9999-12-31 when active
    USER_ID            TEXT,
    CREATED_AT         TIMESTAMPTZ,
    PRIMARY KEY (API_REQ_ID, API_REQ_VID)
);
