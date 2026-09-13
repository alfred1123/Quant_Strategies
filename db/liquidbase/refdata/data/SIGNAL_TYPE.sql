-- seed data
INSERT INTO REFDATA.SIGNAL_TYPE (NAME, DISPLAY_NAME, FUNC_NAME_BAND, FUNC_NAME_BOUNDED, DESCRIPTION, USER_ID, UPDATED_AT)
VALUES
    ('momentum',  'Momentum',  'momentum_band_signal',  'momentum_bounded_signal',  'Go long when factor exceeds threshold',  'alfcheun', now()),
    ('reversion', 'Reversion', 'reversion_band_signal', 'reversion_bounded_signal', 'Go long when factor drops below threshold', 'alfcheun', now()),
    ('momentum_long',  'Momentum (long only)',  'momentum_band_signal_long_only',  'momentum_bounded_signal_long_only',  'Long or flat — never short',  'alfcheun', now()),
    ('reversion_long', 'Reversion (long only)', 'reversion_band_signal_long_only', 'reversion_bounded_signal_long_only', 'Long or flat — never short', 'alfcheun', now());
