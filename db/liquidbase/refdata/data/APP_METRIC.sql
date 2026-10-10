-- seed data for REFDATA.APP_METRIC
-- APP_ID references: 1=yahoo, 2=glassnode, 3=futu
-- Further Glassnode series are in APP_METRIC_GLASSNODE.sql (release 1.28.0).
-- Do not add them here: this file is the archived baseline.
-- Futu OpenD excluded — limited historical depth, not suited for backtesting.
-- Add rows here when providers are activated. See docs/design/alt-data-sources.md
INSERT INTO REFDATA.APP_METRIC (APP_ID, METRIC_NM, DISPLAY_NAME, METRIC_PATH, DATA_CATEGORY, METHOD_NAME, DESCRIPTION, USER_ID, UPDATED_AT)
VALUES
    -- Yahoo Finance (APP_ID=1) — single price metric
    (1, 'price',               'Close Price',          NULL,                                          'PRICE',   'get_historical_price',  'Daily OHLCV close price',                          'alfcheun', now()),

    -- Glassnode (APP_ID=2) — close price. Other series: APP_METRIC_GLASSNODE.sql
    (2, 'price',               'Close Price (USD)',    'market/price_usd_close',                      'PRICE',   'get_historical_price',  'Daily USD close price',                            'alfcheun', now());
