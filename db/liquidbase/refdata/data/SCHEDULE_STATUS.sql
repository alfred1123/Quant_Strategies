INSERT INTO REFDATA.SCHEDULE_STATUS (NAME, DISPLAY_NAME, DESCRIPTION, USER_ID, UPDATED_AT)
VALUES
    ('PENDING', 'Pending', 'Cursor row: the next due time for a scheduled deployment.', 'alfcheun', now()),
    ('SUCCESS', 'Success', 'The scheduled apply ran and the order path completed.',     'alfcheun', now()),
    ('FAILED',  'Failed',  'The scheduled apply did not complete.',                     'alfcheun', now());
