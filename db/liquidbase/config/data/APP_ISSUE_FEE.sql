-- Bybit VIP-0 perpetual. Every Bybit future uses this row (ISSUE_TYPE = future).
INSERT INTO CONFIG.APP_ISSUE_FEE (
    APP_ID,
    ISSUE_TYPE,
    MAKER_BPS,
    TAKER_BPS,
    USER_ID,
    UPDATED_AT
)
SELECT a.APP_ID,
       'future',
       2.0,
       5.5,
       'system',
       NOW() AT TIME ZONE 'UTC'
  FROM REFDATA.APP a
 WHERE a.NAME = 'bybit'
   AND NOT EXISTS (
         SELECT 1
           FROM CONFIG.APP_ISSUE_FEE f
          WHERE f.APP_ID = a.APP_ID
            AND f.ISSUE_TYPE = 'future'
       );
