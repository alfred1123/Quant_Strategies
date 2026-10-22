INSERT INTO CONFIG.SETTING (SETTING_NM, SETTING_VALUE, DESCRIPTION, USER_ID, UPDATED_AT)
VALUES
    ('min_metric_obs',          '60',   'Finite PnL bars below which Sharpe is undefined (decisions #63, #82).',              'alfcheun', now()),
    ('max_queued_per_user',     '30',   'Active QUEUED backtest jobs per user before enqueue returns 429.',                    'alfcheun', now()),
    ('default_tm_interval_id',  '1',    'TM_INTERVAL_ID assumed when a cache read or provider fill names none (daily).',       'alfcheun', now()),
    ('fallback_settlement_ccy', 'USDT', 'Settlement currency recorded on a fill when INST.PRODUCT.CCY is not populated.',    'alfcheun', now()),
    ('order_max_attempts',      '5',    'Broker order submits per apply before the apply is a failure (OrderRetryPolicy).',    'alfcheun', now()),
    ('order_retry_backoff_s',   '2.0',  'Seconds between order submits within one apply.',                                     'alfcheun', now()),
    ('tick_max_attempts',       '3',    'Whole-apply attempts per scheduled tick before the deployment pauses (decision #79).', 'alfcheun', now()),
    ('tick_retry_backoff_s',    '5.0',  'Seconds between whole-apply attempts within one tick.',                               'alfcheun', now()),
    ('fill_confirm_delays_s',   '0.3,0.6,1.2,2.4,3.5', 'fetch_order poll schedule after a market order, comma-separated seconds.', 'alfcheun', now());
