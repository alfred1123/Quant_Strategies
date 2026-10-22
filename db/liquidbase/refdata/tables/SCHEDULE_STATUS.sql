-- TRADE.DEPLOYMENT_SCHEDULE_STATUS.STATUS values. The column has no check
-- constraint; the tick validates against this catalog before the write.
CREATE TABLE REFDATA.SCHEDULE_STATUS (
    SCHEDULE_STATUS_ID  INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    NAME                TEXT NOT NULL UNIQUE,
    DISPLAY_NAME        TEXT,
    DESCRIPTION         TEXT,
    USER_ID             TEXT,
    UPDATED_AT          TIMESTAMPTZ
);
