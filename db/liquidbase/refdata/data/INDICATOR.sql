-- seed data
INSERT INTO REFDATA.INDICATOR (NAME, DISPLAY_NAME, METHOD_NAME, DESCRIPTION, WIN_MIN, WIN_MAX, WIN_STEP, SIG_MIN, SIG_MAX, SIG_STEP, IS_BOUNDED_IND, USER_ID, UPDATED_AT)
VALUES
    ('bollinger', 'Bollinger Band (z-score)', 'get_bollinger_band',        'Bollinger Band z-score indicator',  10, 100, 5,  0.25, 2.50, 0.25, 'N', 'alfcheun', now()),
    ('sma',       'SMA',                      'get_sma',                   'Simple Moving Average',              5, 200, 5,  0.00, 0.10, 0.01, 'N', 'alfcheun', now()),
    ('ema',       'EMA',                      'get_ema',                   'Exponential Moving Average',         5, 200, 5,  0.00, 0.10, 0.01, 'N', 'alfcheun', now()),
    ('rsi',       'RSI',                      'get_rsi',                   'Relative Strength Index',            5,  50, 1,  NULL, NULL,  5.00, 'Y', 'alfcheun', now()),
    ('stochastic','Stochastic Oscillator',    'get_stochastic_oscillator', 'Stochastic Oscillator (%K)',         5,  50, 5,  NULL, NULL,  5.00, 'Y', 'alfcheun', now());
