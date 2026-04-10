-- Each VID stores the FULL history (app fetches only delta from API,
-- merges with previous VID, writes the complete dataset as a new VID).
-- Read path: join on API_REQUEST WHERE IS_CURRENT_IND = 'Y' to find active subscriptions,
--            then SELECT MAX(API_REQ_VID) payload for the latest version.
-- Purge path: DROP partition containing old rows.
CREATE TABLE BT.API_REQUEST_PAYLOAD (
    API_REQ_ID     UUID NOT NULL,
    API_REQ_VID    INTEGER NOT NULL,
    RANGE_START_TS TIMESTAMPTZ NOT NULL,   -- full history start this VID covers
    RANGE_END_TS   TIMESTAMPTZ NOT NULL,   -- full history end this VID covers
    PAYLOAD        JSONB NOT NULL,         -- complete merged history
    USER_ID        TEXT,
    CREATED_AT     TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (API_REQ_ID, API_REQ_VID, CREATED_AT)
) PARTITION BY RANGE (CREATED_AT);

-- pg_partman: automatic yearly partition creation & retention.
-- Requires: CREATE EXTENSION IF NOT EXISTS pg_partman;
-- Schedule run_maintenance() via pg_partman BGW or cron.
SELECT create_parent(
    p_parent_table   := 'bt.api_request_payload',
    p_control        := 'created_at',
    p_interval       := '1 year',
    p_premake        := 2
);

-- Example partitions (auto-created by pg_partman, shown for reference):
-- BT.API_REQUEST_PAYLOAD_p2025 : 2025-01-01 .. 2026-01-01
-- BT.API_REQUEST_PAYLOAD_p2026 : 2026-01-01 .. 2027-01-01
-- BT.API_REQUEST_PAYLOAD_p2027 : 2027-01-01 .. 2028-01-01
-- BT.API_REQUEST_PAYLOAD_p2026_10 : 2026-10-01 .. 2027-01-01
--
-- Purge old partitions:
-- DROP TABLE BT.API_REQUEST_PAYLOAD_p2025_10;
