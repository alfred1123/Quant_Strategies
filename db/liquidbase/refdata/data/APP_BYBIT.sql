-- Phase 1.1 — Bybit broker row (idempotent seed).
INSERT INTO REFDATA.APP (NAME, DISPLAY_NAME, CLASS_NAME, IS_EXCHANGE_IND, DESCRIPTION, USER_ID, UPDATED_AT)
SELECT 'bybit', 'Bybit', 'Bybit', 'Y', 'Bybit REST API trading', 'alfcheun', NOW() AT TIME ZONE 'UTC'
 WHERE NOT EXISTS (
    SELECT 1 FROM REFDATA.APP WHERE NAME = 'bybit'
);
