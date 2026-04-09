-- seed data
INSERT INTO REFDATA.CONJUNCTION (NAME, DISPLAY_NAME, DESCRIPTION, USER_ID, UPDATED_AT)
VALUES
    ('AND', 'AND', 'All factors must agree on direction', 'alfcheun', now()),
    ('OR',  'OR',  'Any factor can trigger a signal',    'alfcheun', now());
