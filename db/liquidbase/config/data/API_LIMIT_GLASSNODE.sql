-- Professional plan, one Glassnode API key (APP_ID = 2).
-- 160000 calls per rolling 30 days. TIME_WINDOW_SEC is seconds, so a
-- calendar month is 2592000 (30 * 24 * 3600). The archived baseline
-- seeded the free tier (10/minute and 200/day). Those rows would still
-- block this key. The short window seen in response headers is not a row.
DELETE FROM CONFIG.API_LIMIT
 WHERE APP_ID = 2
   AND LIMIT_TYPE IN ('requests_per_window', 'requests_per_day');

INSERT INTO CONFIG.API_LIMIT (
    APP_ID, LIMIT_TYPE, MAX_VALUE, TIME_WINDOW_SEC, DESCRIPTION, USER_ID, UPDATED_AT
)
VALUES (
    2, 'requests_per_month', 160000, 2592000,
    'Professional: 160000 calls per 30 days for this API key',
    'alfcheun', now()
);
