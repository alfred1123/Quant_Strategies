-- Nasdaq Data Link provider (APP_ID = 4, follows yahoo=1, glassnode=2, futu=3)
INSERT INTO REFDATA.APP (NAME, DISPLAY_NAME, CLASS_NAME, DESCRIPTION, USER_ID, UPDATED_AT)
VALUES
    ('nasdaq_data_link', 'Nasdaq Data Link', 'NasdaqDataLink', 'Time-series and table data via Nasdaq Data Link API (formerly Quandl)', 'alfcheun', now());
