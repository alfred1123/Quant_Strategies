-- Backtest queue lifecycle states. IS_TERMINAL_IND='Y' marks rows that no
-- longer need worker attention (UI uses it to split active vs. history panes).
--
-- CANCEL_REQUESTED is non-terminal: it represents "user has asked to cancel,
-- worker has not yet acknowledged". The worker observes this state via an
-- in-memory cancel signal from the coordinator (DB row exists for audit, but
-- the running process is signaled out-of-band) and finalizes by inserting a
-- CANCELLED row via SP_INS_QUEUE (IN_ACTION=CANCEL or TERMINAL).
INSERT INTO REFDATA.QUEUE_STATUS (NAME, DISPLAY_NAME, DESCRIPTION, USER_ID, UPDATED_AT)
VALUES
    ('QUEUED',           'Queued',           'Waiting in line for a worker slot.',                                 'alfcheun', now()),
    ('RUNNING',          'Running',          'Worker is executing this job.',                                      'alfcheun', now()),
    ('CANCEL_REQUESTED', 'Cancel requested', 'User asked to cancel a running job; worker has not acknowledged.',  'alfcheun', now()),
    ('COMPLETED',        'Completed',        'Job finished successfully.',                                         'alfcheun', now()),
    ('FAILED',           'Failed',           'Job raised an unhandled exception or worker crashed.',               'alfcheun', now()),
    ('CANCELLED',        'Cancelled',        'Job was cancelled by the user (queued or via cooperative cancel).',  'alfcheun', now());
