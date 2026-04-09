-- seed data
INSERT INTO REFDATA.APP (NAME, DISPLAY_NAME, CLASS_NAME, DESCRIPTION, USER_ID, UPDATED_AT)
VALUES
    ('yahoo',     'Yahoo Finance', 'YahooFinance', 'Free daily OHLCV via yfinance',          'alfcheun', now()),
    ('glassnode', 'Glassnode',     'Glassnode',    'On-chain and market data for crypto',     'alfcheun', now()),
    ('futu',      'Futu OpenD',    'FutuOpenD',    'Futu brokerage real-time and historical', 'alfcheun', now());
