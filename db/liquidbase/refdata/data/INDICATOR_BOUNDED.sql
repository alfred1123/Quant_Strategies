-- Insert stochastic oscillator (added after initial seed)
INSERT INTO REFDATA.INDICATOR (NAME, DISPLAY_NAME, METHOD_NAME, DESCRIPTION, WIN_MIN, WIN_MAX, WIN_STEP, SIG_MIN, SIG_MAX, SIG_STEP, IS_BOUNDED_IND, USER_ID, UPDATED_AT)
VALUES ('stochastic', 'Stochastic Oscillator', 'get_stochastic_oscillator', 'Stochastic Oscillator (%K)', 5, 50, 5, NULL, NULL, 5.00, 'Y', 'alfcheun', now())
ON CONFLICT DO NOTHING;

-- Set IS_BOUNDED_IND flag on existing indicators and NULL out sig bounds for bounded ones
UPDATE REFDATA.INDICATOR SET IS_BOUNDED_IND = 'Y', SIG_MIN = NULL, SIG_MAX = NULL, SIG_STEP = 5.00 WHERE METHOD_NAME = 'get_rsi';
UPDATE REFDATA.INDICATOR SET IS_BOUNDED_IND = 'Y', SIG_MIN = NULL, SIG_MAX = NULL, SIG_STEP = 5.00 WHERE METHOD_NAME = 'get_stochastic_oscillator';
UPDATE REFDATA.INDICATOR SET IS_BOUNDED_IND = 'N' WHERE IS_BOUNDED_IND IS NULL;
