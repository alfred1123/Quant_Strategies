"""ccxt exchange presets keyed by REFDATA.APP name.

Two-layer config (Option C)
---------------------------
* **REFDATA.APP** — broker identity (``app_id``, ``name``, display). Postgres → Redis.
* **CCXT_PRESETS** — ccxt wiring (exchange class, sandbox/demo hooks, auth hints). Code only.

Dict keys in ``CCXT_PRESETS`` MUST match ``REFDATA.APP.NAME``. Registry joins the layers at
startup (:mod:`quant.trade.registry`).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import ccxt


@dataclass(frozen=True)
class ConnectParams:
    """Runtime connect flags — paper/live and exchange-specific demo mode."""

    paper: bool
    demo: bool = False


ExchangeWirer = Callable[[ccxt.Exchange, ConnectParams], None]
AuthHintFn = Callable[[ConnectParams], str]


def _wire_paper_sandbox(exchange: ccxt.Exchange, params: ConnectParams) -> None:
    """Default: ccxt sandbox/testnet when ``paper=True``."""
    if params.paper:
        exchange.set_sandbox_mode(True)


def _wire_bybit(exchange: ccxt.Exchange, params: ConnectParams) -> None:
    """Bybit: disable fetchCurrencies; demo vs testnet vs mainnet."""
    exchange.has["fetchCurrencies"] = False
    if params.demo:
        exchange.enable_demo_trading(True)
        return
    if params.paper:
        exchange.set_sandbox_mode(True)


def _bybit_auth_hint(params: ConnectParams) -> str:
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


@dataclass(frozen=True)
class CcxtExchangePreset:
    """Static ccxt wiring for one REFDATA.APP broker row."""

    exchange_id: str
    exchange_label: str
    default_type: str | None = None
    fetch_order_params: dict | None = field(default=None, compare=False, repr=False)
    wire: ExchangeWirer = field(default=_wire_paper_sandbox, compare=False, repr=False)
    auth_hint: AuthHintFn | None = field(default=None, compare=False, repr=False)


CCXT_PRESETS: dict[str, CcxtExchangePreset] = {
    "bybit": CcxtExchangePreset(
        exchange_id="bybit",
        exchange_label="Bybit",
        default_type="linear",
        fetch_order_params={"acknowledged": True},
        wire=_wire_bybit,
        auth_hint=_bybit_auth_hint,
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
