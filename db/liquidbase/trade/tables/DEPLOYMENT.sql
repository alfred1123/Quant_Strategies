-- TRADE.DEPLOYMENT — live strategy target (one row per apply).
--
-- Soft-versioned: one logical deployment = one DEPLOYMENT_ID (UUID). Config
-- changes (qty, credential, enabled, …) bump DEPLOYMENT_VID, close the prior
-- row (TRANSACT_TO_TS = now()), and insert a new open row
-- (TRANSACT_TO_TS = '9999-12-31') — no UPDATED_AT.
--
-- Links a pinned BT.STRATEGY version to an exchange account (API_CREDENTIAL_ID)
-- and product (INTERNAL_CUSIP). No TRADE.CONNECTION table — broker sessions
-- are ephemeral; audit = TRADE.EXECUTION_EVENT + TRADE.TRANSACTION.
--
-- Phase 1.2: table + SP skeleton. Trade defaults (size overrides, schedules)
-- may extend this table later.
CREATE TABLE TRADE.DEPLOYMENT (
    DEPLOYMENT_ID       UUID NOT NULL,
    DEPLOYMENT_VID      INTEGER NOT NULL,
    APP_USER_ID         UUID NOT NULL,
    STRATEGY_ID         UUID NOT NULL,
    STRATEGY_VID        INTEGER NOT NULL,
    API_CREDENTIAL_ID   INTEGER NOT NULL,
    APP_ID              INTEGER NOT NULL,
    INTERNAL_CUSIP      TEXT NOT NULL,
    QTY                 NUMERIC NOT NULL,
    IS_PAPER_IND        CHAR(1) NOT NULL,
    IS_ENABLED_IND      CHAR(1) NOT NULL,
    DEPLOYMENT_STATUS   TEXT NOT NULL,
    TRANSACT_FROM_TS    TIMESTAMPTZ NOT NULL,
    TRANSACT_TO_TS      TIMESTAMPTZ NOT NULL,
    USER_ID             TEXT NOT NULL,
    CREATED_AT          TIMESTAMPTZ NOT NULL,

    PRIMARY KEY (DEPLOYMENT_ID, DEPLOYMENT_VID)
);

CREATE INDEX IX_DEPLOYMENT_USER_CURRENT
    ON TRADE.DEPLOYMENT (APP_USER_ID, IS_ENABLED_IND, CREATED_AT DESC)
    WHERE TRANSACT_TO_TS = TIMESTAMPTZ '9999-12-31 00:00:00+00';

CREATE INDEX IX_DEPLOYMENT_STRATEGY
    ON TRADE.DEPLOYMENT (STRATEGY_ID, STRATEGY_VID, CREATED_AT DESC);
