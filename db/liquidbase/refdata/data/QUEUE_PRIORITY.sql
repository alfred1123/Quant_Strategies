INSERT INTO REFDATA.QUEUE_PRIORITY (NAME, DISPLAY_NAME, PRIORITY, DESCRIPTION, USER_ID, UPDATED_AT)
VALUES
    ('normal', 'Normal', 100, 'Default. Runs after every high-priority job.', 'alfcheun', now()),
    ('high',   'High',   0,   'Runs ahead of normal jobs.',                   'alfcheun', now());
