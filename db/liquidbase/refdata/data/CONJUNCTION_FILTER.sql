-- Add FILTER conjunction mode: first factor gates on/off, remaining factors provide direction.
INSERT INTO REFDATA.CONJUNCTION (NAME, DISPLAY_NAME, DESCRIPTION, USER_ID, UPDATED_AT)
VALUES
    ('FILTER', 'Filter', 'First factor gates activity; remaining factors set direction', 'alfcheun', now());
