"""Venue trading rules shared by broker adapters."""

from dataclasses import dataclass


@dataclass(frozen=True)
class MarketLimits:
    """The smallest order one venue accepts for one symbol.

    Read live from the broker (ccxt ``load_markets``) rather than seeded into
    REFDATA: an exchange raises a lot size or a notional floor whenever it
    likes, and a stale table would reject orders the venue accepts while
    passing ones it refuses. REFDATA owns values a *user* picks from; this is a
    fact the venue owns.

    Either field is ``None`` when the exchange does not publish that rule, in
    which case it is not enforced here and the broker's own reject text is what
    gets recorded.
    """

    symbol: str
    min_qty: float | None = None
    min_notional: float | None = None

    def undersized(self, qty: float, price: float | None = None) -> str | None:
        """Why the venue would refuse *qty*, or ``None`` when it is big enough.

        *price* is only needed for the notional rule — pass the last traded
        price, or ``None`` to skip that rule when no quote is available.
        """
        if qty <= 0:
            return None
        if self.min_qty is not None and qty < self.min_qty:
            return f"qty {qty:g} is below {self.symbol} min qty {self.min_qty:g}"
        if self.min_notional is not None and price is not None:
            notional = qty * price
            if notional < self.min_notional:
                return (
                    f"notional {notional:g} is below {self.symbol} "
                    f"min notional {self.min_notional:g}"
                )
        return None
