-- Rename FUNC_NAME_BAND values (_const -> _band) and add FUNC_NAME_BOUNDED
UPDATE REFDATA.SIGNAL_TYPE
   SET FUNC_NAME_BAND    = 'momentum_band_signal',
       FUNC_NAME_BOUNDED = 'momentum_bounded_signal'
 WHERE NAME = 'momentum';

UPDATE REFDATA.SIGNAL_TYPE
   SET FUNC_NAME_BAND    = 'reversion_band_signal',
       FUNC_NAME_BOUNDED = 'reversion_bounded_signal'
 WHERE NAME = 'reversion';
