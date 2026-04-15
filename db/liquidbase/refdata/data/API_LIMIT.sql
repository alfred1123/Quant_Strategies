-- API rate limits per provider.
-- APP_IDs: yahoo=1, glassnode=2, futu=3, nasdaq_data_link=4.
-- Limits sourced from provider docs as of 2026-04.
--
-- Nasdaq Data Link (authenticated free tier):
--   300 calls / 10 seconds, 2000 calls / 10 minutes, 50000 calls / day
--   See: https://docs.data.nasdaq.com/docs/rate-limits-1
--
-- Yahoo Finance (yfinance, unofficial scraper):
--   No published limits — conservative default to avoid IP blocks.
--
-- Glassnode (free tier):
--   200 calls / day, 10 calls / minute
--   See: https://docs.glassnode.com/general-info/api-key-tiers
--
-- Futu OpenD:
--   30 requests / 30 seconds (gateway-imposed)
--   See: https://openapi.futunn.com/futu-api-doc/en/intro/authority.html

INSERT INTO REFDATA.API_LIMIT (APP_ID, LIMIT_TYPE, MAX_VALUE, TIME_WINDOW_SEC, DESCRIPTION, USER_ID, UPDATED_AT)
VALUES
    -- Yahoo Finance
    (1, 'requests_per_window',    100,     60, 'Conservative: 100 calls/minute to avoid IP blocks',              'alfcheun', now()),
    -- Glassnode
    (2, 'requests_per_window',     10,     60, 'Free tier: 10 calls/minute',                                     'alfcheun', now()),
    (2, 'requests_per_day',       200,  86400, 'Free tier: 200 calls/day',                                       'alfcheun', now()),
    -- Futu OpenD
    (3, 'requests_per_window',     30,     30, 'Gateway limit: 30 requests/30 seconds',                          'alfcheun', now()),
    -- Nasdaq Data Link (authenticated free tier)
    (4, 'requests_per_window',    300,     10, 'Authenticated free: 300 calls/10 seconds',                       'alfcheun', now()),
    (4, 'requests_per_10min',    2000,    600, 'Authenticated free: 2000 calls/10 minutes',                      'alfcheun', now()),
    (4, 'requests_per_day',     50000,  86400, 'Authenticated free: 50000 calls/day',                            'alfcheun', now());
