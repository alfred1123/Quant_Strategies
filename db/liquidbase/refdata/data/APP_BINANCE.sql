-- Phase 1.1 — Binance broker row (idempotent seed).
INSERT INTO REFDATA.APP (NAME, DISPLAY_NAME, CLASS_NAME, IS_EXCHANGE_IND, DESCRIPTION, USER_ID, UPDATED_AT)
SELECT 'binance', 'Binance', 'Binance', 'Y', 'Binance REST API trading', 'alfcheun', NOW() AT TIME ZONE 'UTC'
 WHERE NOT EXISTS (
    SELECT 1 FROM REFDATA.APP WHERE NAME = 'binance'
);
