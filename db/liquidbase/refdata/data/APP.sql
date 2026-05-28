-- seed data
INSERT INTO REFDATA.APP (NAME, DISPLAY_NAME, CLASS_NAME, IS_EXCHANGE_IND, DESCRIPTION, USER_ID, UPDATED_AT)
VALUES
    ('yahoo',     'Yahoo Finance', 'YahooFinance', 'N', 'Free daily OHLCV via yfinance',          'alfcheun', now()),
    ('glassnode', 'Glassnode',     'Glassnode',    'N', 'On-chain and market data for crypto',     'alfcheun', now()),
    ('futu',      'Futu OpenD',    'FutuOpenD',    'Y', 'Futu brokerage real-time and historical', 'alfcheun', now());
