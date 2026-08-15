-- Bybit + Binance xrefs for btcusdt.crypto (product_id=43).
-- Vendor symbols verified against ccxt public markets.
-- Idempotent: skips if xref already exists for the (product_id, app_id) pair.

-- Fresh restart: truncate processing, cache, and trade tables.
TRUNCATE trade.transaction;
TRUNCATE trade.execution_event;
TRUNCATE trade.deployment_schedule_status;
TRUNCATE trade.deployment;
TRUNCATE market_data.price_bar;
TRUNCATE bt.queue;
TRUNCATE bt.api_request_payload;
TRUNCATE bt.api_request;
TRUNCATE core_admin.log_proc_detail;

DO $$
DECLARE
    V_NEXT_ID INTEGER;
    V_STATE   TEXT;
    V_MSG     TEXT;
    V_ERR     TEXT;
BEGIN
    -- Bybit (app_id=34) → BTCUSDT
    IF NOT EXISTS (
        SELECT 1 FROM INST.PRODUCT_XREF
        WHERE PRODUCT_ID = 43 AND APP_ID = 34
          AND TRANSACT_TO_TS = TIMESTAMPTZ '9999-12-31'
    ) THEN
        SELECT COALESCE(MAX(PRODUCT_XREF_ID), 0) + 1 INTO V_NEXT_ID FROM INST.PRODUCT_XREF;
        CALL INST.SP_INS_PRODUCT_XREF(V_NEXT_ID, 43, 34, 'BTCUSDT', 'liquibase', V_STATE, V_MSG, V_ERR);
        RAISE NOTICE 'Inserted Bybit xref for btcusdt.crypto (xref_id=%)', V_NEXT_ID;
    ELSE
        RAISE NOTICE 'Bybit xref for btcusdt.crypto already exists — skipped';
    END IF;

    -- Binance (app_id=35) → BTCUSDT
    IF NOT EXISTS (
        SELECT 1 FROM INST.PRODUCT_XREF
        WHERE PRODUCT_ID = 43 AND APP_ID = 35
          AND TRANSACT_TO_TS = TIMESTAMPTZ '9999-12-31'
    ) THEN
        SELECT COALESCE(MAX(PRODUCT_XREF_ID), 0) + 1 INTO V_NEXT_ID FROM INST.PRODUCT_XREF;
        CALL INST.SP_INS_PRODUCT_XREF(V_NEXT_ID, 43, 35, 'BTCUSDT', 'liquibase', V_STATE, V_MSG, V_ERR);
        RAISE NOTICE 'Inserted Binance xref for btcusdt.crypto (xref_id=%)', V_NEXT_ID;
    ELSE
        RAISE NOTICE 'Binance xref for btcusdt.crypto already exists — skipped';
    END IF;
END $$;
