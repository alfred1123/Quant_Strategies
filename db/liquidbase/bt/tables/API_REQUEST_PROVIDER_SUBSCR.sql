-- The stored window belongs with the subscription, in MARKET_DATA.
-- Partitions are separate relations, so a parent move can leave them in bt.
-- Move any that stayed behind. pg_partman, when present, follows the parent.

ALTER TABLE BT.API_REQUEST SET SCHEMA MARKET_DATA;

ALTER TABLE BT.API_REQUEST_PAYLOAD SET SCHEMA MARKET_DATA;

DO $$
DECLARE
    V_PART RECORD;
BEGIN
    FOR V_PART IN
        SELECT child_ns.nspname AS child_schema,
               child.relname    AS child_name
          FROM pg_inherits i
          JOIN pg_class parent ON parent.oid = i.inhparent
          JOIN pg_namespace parent_ns ON parent_ns.oid = parent.relnamespace
          JOIN pg_class child ON child.oid = i.inhrelid
          JOIN pg_namespace child_ns ON child_ns.oid = child.relnamespace
         WHERE parent_ns.nspname = 'market_data'
           AND parent.relname = 'api_request_payload'
           AND child_ns.nspname <> 'market_data'
    LOOP
        EXECUTE format(
            'ALTER TABLE %I.%I SET SCHEMA market_data',
            V_PART.child_schema, V_PART.child_name
        );
    END LOOP;

    IF to_regclass('partman.part_config') IS NOT NULL THEN
        UPDATE partman.part_config
           SET parent_table = 'market_data.api_request_payload'
         WHERE parent_table = 'bt.api_request_payload';
    END IF;
END $$;

ALTER TABLE MARKET_DATA.API_REQUEST
    ADD COLUMN PROVIDER_SUBSCR_ID UUID;

CREATE UNIQUE INDEX UQ_API_REQUEST_SUBSCR_OPEN
    ON MARKET_DATA.API_REQUEST (PROVIDER_SUBSCR_ID)
    WHERE TRANSACT_TO_TS = TIMESTAMPTZ '9999-12-31 00:00:00+00'
      AND PROVIDER_SUBSCR_ID IS NOT NULL;
