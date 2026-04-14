-- Set sig_min/sig_max for bounded indicators (always 0–100 range)
UPDATE REFDATA.INDICATOR SET SIG_MIN = 0, SIG_MAX = 100 WHERE METHOD_NAME = 'get_rsi';
UPDATE REFDATA.INDICATOR SET SIG_MIN = 0, SIG_MAX = 100 WHERE METHOD_NAME = 'get_stochastic_oscillator';
