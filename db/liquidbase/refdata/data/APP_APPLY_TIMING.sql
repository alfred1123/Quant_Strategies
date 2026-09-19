-- Bybit/Binance × DAILY/1H — 5 min after bar close (matches trade_apply_tick :05 UTC).
INSERT INTO REFDATA.APP_APPLY_TIMING (
    APP_ID,
    TM_INTERVAL_ID,
    EXECUTE_OFFSET,
    USER_ID,
    UPDATED_AT
)
SELECT a.APP_ID,
       ti.TM_INTERVAL_ID,
       INTERVAL '5 minutes',
       'system',
       NOW() AT TIME ZONE 'UTC'
  FROM REFDATA.APP a
 CROSS JOIN REFDATA.TM_INTERVAL ti
 WHERE a.IS_EXCHANGE_IND = 'Y'
   AND a.NAME IN ('bybit', 'binance')
   AND NOT EXISTS (
         SELECT 1
           FROM REFDATA.APP_APPLY_TIMING t
          WHERE t.APP_ID = a.APP_ID
            AND t.TM_INTERVAL_ID = ti.TM_INTERVAL_ID
       );
