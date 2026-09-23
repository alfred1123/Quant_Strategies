"""ccxt exchange presets keyed by REFDATA.APP name.

Two-layer config (Option C)
---------------------------
* **REFDATA.APP** — broker identity (``app_id``, ``name``, display). Postgres → Redis.
* **CCXT_PRESETS** — ccxt wiring (exchange class, category, venue behaviour). Code only.

Dict keys in ``CCXT_PRESETS`` MUST match ``REFDATA.APP.NAME``. Registry joins the layers at
startup (:mod:`quant.trade.registry`).

Venue-specific behaviour lives on a :class:`CcxtVenue` subclass, not in the
gateway: :class:`CcxtVenue` is what ccxt does out of the box, and a venue
overrides only where it differs.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

import ccxt

from quant.trade.models.key_profile import ApiKeyInfo
from quant.trade.models.order import OrderRejectReason

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ConnectParams:
    """Runtime connect flags — paper/live and exchange-specific demo mode."""

    paper: bool
    demo: bool = False


class CcxtVenue:
    """ccxt's default behaviour for a venue; subclasses override where theirs differs."""

    def wire(self, exchange: ccxt.Exchange, params: ConnectParams) -> None:
        """Point the exchange at the right environment before first use."""
        if params.paper:
            exchange.set_sandbox_mode(True)

    def auth_hint(self, params: ConnectParams) -> str:
        """Extra sentence appended to a credential rejection; empty for none."""
        return ""

    def fetch_api_key_info(self, exchange: ccxt.Exchange) -> ApiKeyInfo | None:
        """The venue's description of the session's own key; ``None`` if it has no such call."""
        return None

    def classify_denial(self, exc: ccxt.BaseError) -> OrderRejectReason | None:
        """Name a refusal the platform acts on differently from a bad key.

        Returning ``IP_NOT_ALLOWED`` is what lets a key be routed: a venue that
        cannot say its refusal was about the source IP leaves nothing to try
        another route on.
        """
        return None


class BybitVenue(CcxtVenue):
    _RET_CODE = re.compile(r'"retCode"\s*:\s*(\d+)')
    _DENIALS = {
        "10010": OrderRejectReason.IP_NOT_ALLOWED,
        "10024": OrderRejectReason.REGION_RESTRICTED,
    }

    def wire(self, exchange: ccxt.Exchange, params: ConnectParams) -> None:
        """Disable fetchCurrencies; demo vs testnet vs mainnet."""
        exchange.has["fetchCurrencies"] = False
        if params.demo:
            exchange.enable_demo_trading(True)
            return
        if params.paper:
            exchange.set_sandbox_mode(True)

    def auth_hint(self, params: ConnectParams) -> str:
        if params.demo:
            return (
                " Demo mode uses Bybit Demo Trading (api-demo.bybit.com) — create keys on "
                "www.bybit.com under Demo Trading, not testnet.bybit.com."
            )
        if params.paper:
            return (
                " Paper/testnet mode uses https://testnet.bybit.com/ — mainnet and "
                "Demo Trading keys will not work. Run: "
                "scripts/bybit_local_testnet.py --diagnose"
            )
        return ""

    def fetch_api_key_info(self, exchange: ccxt.Exchange) -> ApiKeyInfo:
        """``GET /v5/user/query-api`` — the key's allowlist, KYC region, and mode.

        Bybit writes ``["*"]`` for an unrestricted allowlist and ``readOnly`` as
        ``0``/``1``.
        """
        result = exchange.private_get_v5_user_query_api().get("result") or {}
        return ApiKeyInfo(
            ips=tuple(result.get("ips") or ()),
            kyc_region=result.get("kycRegion") or None,
            read_only=str(result.get("readOnly")) == "1",
            expires_at=result.get("expiredAt") or None,
        )

    def classify_denial(self, exc: ccxt.BaseError) -> OrderRejectReason | None:
        """Bybit's ``retCode`` out of the response ccxt embeds in the message.

        ccxt maps both codes to ``PermissionDenied``, which is also what a revoked
        key raises, so the class alone cannot tell them apart.
        """
        match = self._RET_CODE.search(str(exc))
        return self._DENIALS.get(match.group(1)) if match else None


@dataclass(frozen=True)
class CcxtExchangePreset:
    """Static ccxt wiring for one REFDATA.APP broker row."""

    exchange_id: str
    exchange_label: str
    default_type: str | None = None
    fetch_order_params: dict | None = field(default=None, compare=False, repr=False)
    venue: CcxtVenue = field(default_factory=CcxtVenue, compare=False, repr=False)

    @property
    def market_type(self) -> str:
        """The product category this preset's sessions trade, for per-key restrictions."""
        return self.default_type or "default"


CCXT_PRESETS: dict[str, CcxtExchangePreset] = {
    "bybit": CcxtExchangePreset(
        exchange_id="bybit",
        exchange_label="Bybit",
        default_type="linear",
        fetch_order_params={"acknowledged": True},
        venue=BybitVenue(),
    ),
    "binance": CcxtExchangePreset(
        exchange_id="binanceusdm",
        exchange_label="Binance",
        default_type=None,
    ),
}


def preset_for_app(app_name: str) -> CcxtExchangePreset:
    """Lookup preset by REFDATA.APP.NAME."""
    try:
        return CCXT_PRESETS[app_name]
    except KeyError as exc:
        raise KeyError(
            f"No CCXT_PRESETS entry for REFDATA.APP name={app_name!r}"
        ) from exc
