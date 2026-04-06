-- seed data
INSERT INTO REFDATA.ASSET_TYPE (NAME, DISPLAY_NAME, TRADING_PERIOD, DESCRIPTION, USER_ID, UPDATED_AT)
VALUES
    ('crypto', 'Crypto (365 days/year)',           365, '24/7/365 trading',            'alfcheun', now()),
    ('equity', 'Equity (252 trading days/year)',   252, 'NYSE/NASDAQ trading days',    'alfcheun', now());
