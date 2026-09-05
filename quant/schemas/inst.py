"""Pydantic schemas for the INST product master — creating an instrument.

An "instrument" is not one table. Identity lives on ``INST.PRODUCT`` under an
``INTERNAL_CUSIP``, and what each venue calls it lives on
``INST.PRODUCT_XREF``. Both are needed before anything can use it, so one
request carries both halves — hence a request shape that is a product plus a
single ``(app_id, vendor_symbol)`` pair rather than two endpoints.

There is no owner field, by design. A product is a shared platform fact in the
same way a bar subscription is: every user sees the same instrument list, so
there is nothing for an owner to scope. ``USER_ID`` is written for audit only
and is never read back.

This module is also where a bad request is refused. ``INST.SP_INS_PRODUCT`` and
``SP_INS_PRODUCT_XREF`` do no validation: the database's half is ``NOT NULL`` on
the columns plus ``UQ_PRODUCT_CUSIP_CURRENT`` / ``UQ_PRODUCT_XREF_CURRENT``,
which report a violated constraint rather than which field was wrong. So a
missing or malformed value has to be a 422 from here, not a 400 from a write.
"""

import re

from pydantic import BaseModel, Field, field_validator

#: ``{symbol}.{suffix}``, lowercase, no whitespace — the whole of the documented
#: cusip rule (decision #21). Deliberately not an allowlist of suffixes: the
#: docs give ``.crypto``, ``.nasdaq``, ``.nyse`` and exchange-specific perp
#: suffixes as examples, not as a closed set, and refusing an unlisted venue
#: would be a rule nothing has agreed to.
_CUSIP_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*\.[a-z0-9][a-z0-9_-]*$")


class CreateInstrumentRequest(BaseModel):
    """A new product and the first venue that lists it.

    The venue half is required rather than optional. A product with no xref is
    invisible to every venue-scoped read — the per-app product list is built
    *from* the xrefs — so a product on its own cannot be subscribed to,
    backtested or deployed, and creating one would look like a failure.
    """

    #: Stable identity, and the value every other schema stores. Normalised to
    #: lowercase here because the rule is a convention rather than a constraint
    #: (``INST.PRODUCT`` has no CHECK), and ``UQ_PRODUCT_CUSIP_CURRENT`` is
    #: case-sensitive: ``BTCUSDT.crypto`` would be accepted as a second,
    #: unrelated instrument that silently forks every downstream lookup.
    internal_cusip: str = Field(min_length=3, examples=["btcusdt.crypto"])
    #: What a human reads in a dropdown. The cusip is not that — nobody
    #: recognises ``ibit.nasdaq`` faster than ``iShares Bitcoin Trust``.
    display_nm: str = Field(min_length=1, examples=["Bitcoin / USDT"])
    #: ``REFDATA.ASSET_TYPE``. Carries the trading calendar, so it decides how
    #: a backtest annualises: 365 days for crypto, ~252 for a listed equity.
    asset_type_id: int
    #: Listing / clearing venue, for equities. **NULL on ``.crypto`` spot** —
    #: the broker belongs in the xref and the deployment, not in the product's
    #: identity, or the same coin becomes two instruments per exchange.
    exchange: str | None = None
    #: The currency the pair is quoted in, e.g. ``USDT``. Not derivable from the
    #: cusip: ``btcusdt.crypto`` trades against USDT while a ``btc-usd`` proxy
    #: on a research vendor does not, and the difference is a real basis.
    ccy: str | None = None
    description: str | None = None
    #: ``REFDATA.APP`` — the venue this first mapping is for. One venue, one
    #: symbol: the same instrument on two exchanges is one product with two
    #: xrefs, so listing it elsewhere is a second write, not a second product.
    app_id: int
    #: The ticker that venue itself prints, exact case (ccxt format for
    #: exchanges), e.g. ``BTCUSDT``. This is the only string capture and
    #: execution can actually send to the venue.
    vendor_symbol: str = Field(min_length=1, examples=["BTCUSDT"])

    @field_validator("internal_cusip")
    @classmethod
    def _normalise_cusip(cls, value: str) -> str:
        cusip = value.strip().lower()
        if not _CUSIP_RE.match(cusip):
            raise ValueError(
                "internal_cusip must be lowercase {symbol}.{suffix} with no "
                "spaces, e.g. btcusdt.crypto — and must name the instrument, "
                "not the broker: btcusdt.bybit is wrong, because Bybit and "
                "Binance share one product and differ only in their xref"
            )
        return cusip

    @field_validator("display_nm", "vendor_symbol")
    @classmethod
    def _strip_required(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped

    @field_validator("exchange", "ccy", "description")
    @classmethod
    def _blank_is_absent(cls, value: str | None) -> str | None:
        """An empty form field means "not set", not an empty string.

        ``EXCHANGE = ''`` on a crypto row would satisfy the "NULL on .crypto
        spot" rule to the letter and break it in practice, since nothing
        downstream tests for the empty string.
        """
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class VenueSymbol(BaseModel):
    """One ticker a venue prints, offered so the symbol need not be typed.

    Read live from the exchange rather than from anything stored: this is the
    set of symbols that *could* be mapped, which is precisely the set the
    platform does not know yet.
    """

    #: Exactly what would go in ``INST.PRODUCT_XREF.VENDOR_SYMBOL``.
    vendor_symbol: str
    base: str | None = None
    quote: str | None = None
    #: What the venue serves under this id — ``["spot", "swap"]`` where one
    #: ticker means both, which Bybit does for every major pair.
    market_types: list[str] = []


class CreatedInstrument(BaseModel):
    """The instrument as the platform now holds it, both halves.

    Read back from the reloaded cache rather than echoed from the request, so
    what comes back is what every dropdown will serve — including the
    ``PRODUCT_ID`` and the version, which the procedure chose and the caller
    could not have known.
    """

    product_id: int
    product_vid: int
    internal_cusip: str
    display_nm: str
    #: Not nullable here even though the column is: the request requires it, so
    #: anything created through this route has one. ``INST.PRODUCT`` rows
    #: predating it may not, which is a read-path concern, not this response's.
    asset_type_id: int
    exchange: str | None = None
    ccy: str | None = None
    description: str | None = None
    #: The first venue mapping, so the response proves the product is visible
    #: to that venue's list rather than leaving the caller to check.
    app_id: int
    vendor_symbol: str
    product_xref_id: int
    product_xref_vid: int
