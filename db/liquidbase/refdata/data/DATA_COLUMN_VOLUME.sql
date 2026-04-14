-- Seed: add Volume data column
INSERT INTO REFDATA.DATA_COLUMN (NAME, DISPLAY_NAME, COLUMN_NAME, DESCRIPTION, USER_ID, UPDATED_AT)
VALUES
    ('volume', 'Volume', 'Volume', 'Trading volume', 'alfcheun', now());
