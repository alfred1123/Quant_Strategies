-- seed data
INSERT INTO REFDATA.INDICATOR (NAME, DISPLAY_NAME, METHOD_NAME, DESCRIPTION, USER_ID, UPDATED_AT)
VALUES
    ('bollinger', 'Bollinger Band (z-score)', 'get_bollinger_band', 'Bollinger Band z-score indicator', 'alfcheun', now()),
    ('sma',       'SMA',                      'get_sma',            'Simple Moving Average',            'alfcheun', now()),
    ('ema',       'EMA',                      'get_ema',            'Exponential Moving Average',       'alfcheun', now()),
    ('rsi',       'RSI',                      'get_rsi',            'Relative Strength Index',          'alfcheun', now());
