-- seed data
INSERT INTO REFDATA.SIGNAL_TYPE (NAME, DISPLAY_NAME, FUNC_NAME, DESCRIPTION, USER_ID, UPDATED_AT)
VALUES
    ('momentum',  'Momentum',  'momentum_const_signal',  'Go long when factor exceeds threshold',  'alfcheun', now()),
    ('reversion', 'Reversion', 'reversion_const_signal', 'Go long when factor drops below threshold', 'alfcheun', now());
