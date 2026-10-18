-- The stored window points at the subscription that asked for it.
-- Existing rows stay null until a subscribe writes the id.
ALTER TABLE BT.API_REQUEST
    ADD COLUMN PROVIDER_SUBSCR_ID UUID;

-- One open window per subscription. The Data tab probes this index.
CREATE UNIQUE INDEX UQ_API_REQUEST_SUBSCR_OPEN
    ON BT.API_REQUEST (PROVIDER_SUBSCR_ID)
    WHERE TRANSACT_TO_TS = TIMESTAMPTZ '9999-12-31 00:00:00+00'
      AND PROVIDER_SUBSCR_ID IS NOT NULL;
