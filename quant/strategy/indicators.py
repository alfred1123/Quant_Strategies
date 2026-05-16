"""Technical analysis indicators operating on a 'factor' column.

Each method returns a ``pd.Series`` aligned with the input DataFrame.
Pure pandas/numpy — no I/O, no external state.
"""

import logging

logger = logging.getLogger(__name__)


class TechnicalAnalysis:
    """Technical analysis indicators operating on a 'factor' column."""

    def __init__(self, data) -> None:
        if 'factor' not in data.columns:
            logger.error("DataFrame missing required 'factor' column, got: %s",
                         list(data.columns))
            raise ValueError("DataFrame must contain a 'factor' column")
        self.data = data
        logger.debug("TechnicalAnalysis initialized with %d rows", len(data))

    def get_sma(self, period):
        """Simple moving average."""
        sma = self.data['factor'].rolling(window=period).mean()
        return sma

    def get_ema(self, period):
        """Exponential moving average."""
        ema = self.data['factor'].ewm(span=period, adjust=False).mean()
        return ema

    def get_rsi(self, period):
        """Relative Strength Index (0-100)."""
        delta = self.data['factor'].diff(1)
        delta = delta.dropna()
        up = delta.copy()
        down = delta.copy()
        up[up < 0] = 0
        down[down > 0] = 0
        roll_up1 = up.rolling(window=period).mean()
        roll_down1 = down.abs().rolling(window=period).mean()
        RS1 = roll_up1 / roll_down1
        rsi = 100.0 - (100.0 / (1.0 + RS1))
        return rsi

    def get_bollinger_band(self, period):
        """Bollinger Band z-score."""
        sma = self.data['factor'].rolling(window=period).mean()
        rstd = self.data['factor'].rolling(window=period).std()
        z = (self.data['factor'] - sma) / rstd
        return z

    def get_stochastic_oscillator(self, period):
        """Stochastic oscillator (%D — smoothed).

        Requires 'High', 'Low', 'Close' columns in data.
        """
        high = self.data['High'].rolling(window=period).max()
        low = self.data['Low'].rolling(window=period).min()
        k = 100 * (self.data['Close'] - low) / (high - low)
        d = k.rolling(window=period).mean()
        return d
