-- Seed REFDATA.TM_INTERVAL — shared by BT.API_REQUEST, MARKET_DATA.PRICE_BAR,
-- and TRADE.DEPLOYMENT scheduler columns.
--
-- TM_INTERVAL_ID = 1 (DAILY) matches BacktestCache.DEFAULT_TM_INTERVAL_ID.
-- PERIOD_LENGTH drives scheduler due-check (SP_GET_MISSED_DUE_DEPLOYMENTS) — add new
-- intervals here only; no CASE in trade procs.
-- DISPLAY_NAME is the schedule dropdown label; NAME stays the machine value, so a new
-- interval is visible in the UI without a frontend change.
INSERT INTO REFDATA.TM_INTERVAL (
    TM_INTERVAL_ID,
    NAME,
    DISPLAY_NAME,
    DESCRIPTION,
    PERIOD_LENGTH,
    USER_ID,
    UPDATED_AT
)
OVERRIDING SYSTEM VALUE
VALUES
    (
        1,
        'DAILY',
        'Daily',
        'Daily bars — matches BacktestCache.DEFAULT_TM_INTERVAL_ID = 1',
        INTERVAL '1 day',
        'system',
        NOW()
    ),
    (
        2,
        '1H',
        'Hourly',
        'Hourly bars',
        INTERVAL '1 hour',
        'system',
        NOW()
    );
