CREATE TABLE CORE_ADMIN.LOG_PROC_DETAIL (
    SCHEMA_NM          TEXT NOT NULL,
    PROC_NM            TEXT NOT NULL,
    CREATED_AT         TIMESTAMPTZ NOT NULL,
    END_AT             TIMESTAMPTZ NOT NULL,
    OTHER_TEXT         TEXT,                  -- input parameters snapshot
    DURATION           DOUBLE PRECISION,
    USER_ID            TEXT
);
