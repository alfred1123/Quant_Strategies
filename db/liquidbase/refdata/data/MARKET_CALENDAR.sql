-- Default calendar for products with EXCHANGE NULL (.crypto) — UTC 24/7, ccxt midnight dailies.
INSERT INTO REFDATA.MARKET_CALENDAR (
    LISTING_EXCHANGE,
    BAR_TIMEZONE,
    MARKET_OPEN_TIME,
    MARKET_CLOSE_TIME,
    USER_ID,
    UPDATED_AT
)
SELECT '',
       'UTC',
       NULL,
       NULL,
       'system',
       NOW() AT TIME ZONE 'UTC'
 WHERE NOT EXISTS (
       SELECT 1 FROM REFDATA.MARKET_CALENDAR WHERE LISTING_EXCHANGE = ''
 );
