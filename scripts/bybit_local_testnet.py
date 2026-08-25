#!/usr/bin/env python3
"""Local Bybit validation harness — golden source before changing trade code.

Run the full matrix (recommended before any trade-layer change):

  .venv/bin/python scripts/bybit_local_testnet.py --suite

Individual steps (same code paths the suite calls):

  --check              Local prereqs (DB, Fernet, keys)
  --diagnose           Which Bybit env accepts your key (testnet/demo/mainnet)
  --save               Persist BYBIT_TESTNET_* keys to CORE_ADMIN.API_CREDENTIAL
  --gateway            ccxt connect + xref + position (+ balance when available)
  --refresh-data       Refresh strategy price cache (Yahoo per strategy config)
  --dry-run            Full deployment dry-run (signal + broker, no orders)
  --dry-run --refresh-data   Dry-run with fresh cache (avoids CacheMissError)
  --api-dry-run        Same dry-run via POST /api/v1/trade/deployments/dry-run
  --intended-matrix    Golden table for signal × position → BUY/SELL/HOLD
  --probe-intended     Live position + intended_side for signals -1/0/1
  --apply-signal S     Preview action for signal S against live position (BUY/SELL/
                        HOLD/OPEN_SHORT/CLOSE_SHORT); add --confirm to place the order
  --apply-signal S --confirm [--qty Q]   Actually place the market order on testnet

Flags:
  --demo               Bybit Demo Trading (not testnet sandbox)
  CCXT_ITEST_PAPER=false   Mainnet keys (legacy bybit._trade.py path)

Env: EXCHANGE_SECRETS_KEY, CCXT_ITEST_* — see .env.example ccxt block.

Suite output: PASS / FAIL / SKIP / WARN per step; exit 1 if any FAIL.
Use --json for machine-readable results (CI golden diff).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Literal
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

from quant.shared.config import LOCAL, db_settings

load_dotenv(ROOT / ".env")

BYBIT_APP_ID = 34
BTCUSDT_PRODUCT_ID = 43
BYBIT_VENDOR_SYMBOL = "BTCUSDT"

# Mirror quant/trade/brokers/ccxt/adapter.py::CcxtTradeAdapter.intended_side — keep in sync.
def _golden_intended_side(signal: float, position_qty: float) -> str:
    from quant.trade.adapters.base import TradeAdapter
    return TradeAdapter.intended_side(signal, position_qty)


StepStatus = Literal["PASS", "FAIL", "SKIP", "WARN"]

# Golden reference: TradeAdapter.intended_side (quant/trade/adapters/base.py)
INTENDED_SIDE_GOLDEN: list[tuple[float, float, str]] = [
    (1.0, 0.0, "BUY"),
    (1.0, 0.01, "HOLD"),
    (1.0, -0.5, "CLOSE_SHORT"),
    (0.0, 0.0, "HOLD"),
    (0.0, 0.01, "SELL"),
    (0.0, -0.5, "CLOSE_SHORT"),
    (-1.0, 0.0, "OPEN_SHORT"),
    (-1.0, 0.01, "SELL"),
    (-1.0, -0.5, "HOLD"),
]


@dataclass
class StepResult:
    step: str
    status: StepStatus
    detail: str = ""
    data: dict = field(default_factory=dict)


@dataclass
class SuiteReport:
    results: list[StepResult] = field(default_factory=list)

    def add(self, result: StepResult) -> StepResult:
        self.results.append(result)
        _print_step(result)
        return result

    @property
    def failed(self) -> bool:
        return any(r.status == "FAIL" for r in self.results)

    def summary(self) -> None:
        counts = {s: 0 for s in ("PASS", "FAIL", "SKIP", "WARN")}
        for r in self.results:
            counts[r.status] += 1
        print(
            f"\n[suite] {counts['PASS']} passed, {counts['FAIL']} failed, "
            f"{counts['SKIP']} skipped, {counts['WARN']} warned"
        )
        if self.failed:
            print("[suite] FAILED — fix failures before changing trade code")
        else:
            print("[suite] OK — golden harness clean")


def _print_step(result: StepResult) -> None:
    tag = f"[{result.status:4}]"
    line = f"{tag} {result.step}"
    if result.detail:
        line += f" — {result.detail}"
    print(line)


def _run_step(name: str, fn) -> StepResult:
    try:
        detail, data = fn()
        return StepResult(name, "PASS", detail, data or {})
    except SystemExit as exc:
        return StepResult(name, "FAIL", str(exc) or "SystemExit")
    except Exception as exc:
        return StepResult(name, "FAIL", f"{type(exc).__name__}: {exc}")


def _skip_step(name: str, reason: str) -> StepResult:
    return StepResult(name, "SKIP", reason)


def _warn_step(name: str, detail: str, *, data: dict | None = None) -> StepResult:
    return StepResult(name, "WARN", detail, data or {})


def _local_conninfo() -> str:
    """DSN for the local database, from ``config/db-targets.json``.

    Pinned to ``local`` rather than following ``DB_TARGET``: this script places
    real orders and writes fills, so it must never be one stray variable away
    from doing that against Aurora.
    """
    override = os.getenv("QUANTDB_CONNINFO")
    if override:
        return override
    settings = db_settings(LOCAL)
    return (
        "host={host} port={port} dbname={dbname} user={user} "
        "password={password} sslmode={sslmode} connect_timeout=5".format(**settings)
    )


def _env_uuid(name: str) -> UUID:
    return UUID(os.environ[name])


def _env_int(name: str) -> int:
    return int(os.environ[name])


def ensure_bybit_xref(conninfo: str) -> None:
    """Insert btcusdt.crypto → BTCUSDT for Bybit if missing."""
    import psycopg

    with psycopg.connect(conninfo) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1 FROM inst.product_xref px
                JOIN inst.product p ON p.product_id = px.product_id
                WHERE p.internal_cusip = 'btcusdt.crypto'
                  AND px.app_id = %s
                  AND px.transact_to_ts > now()
                """,
                (BYBIT_APP_ID,),
            )
            if cur.fetchone():
                print("[xref] btcusdt.crypto → Bybit already mapped")
                return
            cur.execute("SELECT COALESCE(MAX(product_xref_id), 0) + 1 FROM inst.product_xref")
            xref_id = cur.fetchone()[0]
            cur.execute(
                "CALL inst.sp_ins_product_xref(%s, %s, %s, %s, 'bybit_local_testnet', NULL, NULL, NULL)",
                (xref_id, BTCUSDT_PRODUCT_ID, BYBIT_APP_ID, BYBIT_VENDOR_SYMBOL),
            )
        conn.commit()
    print(
        f"[xref] inserted product_xref_id={xref_id} "
        f"btcusdt.crypto → {BYBIT_VENDOR_SYMBOL} (app_id={BYBIT_APP_ID})"
    )


def resolve_api_keys(conninfo: str) -> tuple[str, str]:
    """Load Bybit keys from env (testnet/mainnet aliases) or local DB credential."""
    direct_key = (
        os.getenv("BYBIT_TESTNET_API_KEY")
        or os.getenv("BYBIT_API_KEY")
        or os.getenv("CCXT_ITEST_API_KEY")
    )
    direct_secret = (
        os.getenv("BYBIT_TESTNET_API_SECRET")
        or os.getenv("BYBIT_SECRET_KEY")
        or os.getenv("CCXT_ITEST_API_SECRET")
    )
    if direct_key and direct_secret:
        return direct_key.strip(), direct_secret.strip()

    from quant.api.credentials.repo import ApiCredentialRepo
    from quant.api.credentials.service import CredentialService
    from quant.shared.secrets_crypto import CredentialCrypto

    app_user_id = _env_uuid("CCXT_ITEST_USER_ID")
    cred_id = _env_int("CCXT_ITEST_CREDENTIAL_ID")
    repo = ApiCredentialRepo(conninfo, user_id="bybit_local_testnet")
    svc = CredentialService(CredentialCrypto())
    keys = svc.decrypt_credential(repo, app_user_id, cred_id)
    if keys is None:
        raise SystemExit(
            f"Cannot decrypt credential {cred_id} — set BYBIT_TESTNET_* / BYBIT_API_KEY "
            "in env or re-save with --save"
        )
    api_key, api_secret = keys
    if not api_key or not api_secret:
        raise SystemExit("Decrypted credentials are empty")
    return api_key, api_secret


def diagnose_bybit_keys(api_key: str, api_secret: str) -> None:
    """Try testnet, demo, and mainnet — report which environment accepts the key."""
    import ccxt

    modes = (
        ("testnet", {"sandbox": True, "demo": False}),
        ("demo", {"sandbox": False, "demo": True}),
        ("mainnet", {"sandbox": False, "demo": False}),
    )
    print("[diagnose] Probing Bybit key against testnet / demo / mainnet …")
    print(f"[diagnose] Key prefix: {api_key[:4]}…{api_key[-4:]} (length {len(api_key)})")

    for name, flags in modes:
        ex = ccxt.bybit(
            {
                "apiKey": api_key,
                "secret": api_secret,
                "enableRateLimit": True,
                "options": {"defaultType": "linear"},
            }
        )
        ex.has["fetchCurrencies"] = False
        try:
            if flags["demo"]:
                ex.enable_demo_trading(True)
            elif flags["sandbox"]:
                ex.set_sandbox_mode(True)
            ex.load_markets()
            ex.fetch_balance()
            host = ex.urls.get("api", {})
            api_host = host.get("private") or host.get("futures") or str(host)
            print(f"[diagnose] OK  {name:8} → use this mode (api: {api_host})")
        except ccxt.AuthenticationError as exc:
            print(f"[diagnose] FAIL {name:8} → 10003 invalid key for this environment ({exc})")
        except ccxt.BaseError as exc:
            print(f"[diagnose] FAIL {name:8} → {type(exc).__name__}: {exc}")
        finally:
            try:
                ex.close()
            except Exception:
                pass

    print()
    print("Where to create keys:")
    print("  testnet  → https://testnet.bybit.com/     (Paper mode in Quant_Strategies)")
    print("  demo     → https://www.bybit.com/ Demo Trading  (run with --demo)")
    print("  mainnet  → https://www.bybit.com/ API Management (legacy bybit._trade.py; live only)")


def save_credential(conninfo: str, app_user_id: UUID) -> int:
    """Save Bybit testnet keys from BYBIT_TESTNET_API_KEY/SECRET env vars."""
    api_key = os.getenv("BYBIT_TESTNET_API_KEY", "").strip()
    api_secret = os.getenv("BYBIT_TESTNET_API_SECRET", "").strip()
    if not api_key or not api_secret:
        raise SystemExit(
            "Set BYBIT_TESTNET_API_KEY and BYBIT_TESTNET_API_SECRET to --save"
        )

    from quant.api.credentials.repo import ApiCredentialRepo
    from quant.api.credentials.service import CredentialService
    from quant.shared.secrets_crypto import CredentialCrypto

    app_id = _env_int("CCXT_ITEST_APP_ID") if os.getenv("CCXT_ITEST_APP_ID") else BYBIT_APP_ID
    repo = ApiCredentialRepo(conninfo, user_id="bybit_local_testnet")
    svc = CredentialService(CredentialCrypto())
    row = svc.create_credential(
        repo,
        app_user_id=app_user_id,
        app_id=app_id,
        label="Bybit testnet (local script)",
        api_key=api_key,
        api_secret=api_secret,
    )
    cred_id = row.api_credential_id
    print(f"[credentials] saved api_credential_id={cred_id} (masked {row.api_key_masked})")
    return cred_id


def run_gateway(paper: bool, *, bybit_demo: bool = False) -> None:
    """Connect to Bybit via ccxt and validate credentials."""
    from quant.data.instruments import InstrumentCache
    from quant.trade.brokers.ccxt.adapter import create_ccxt_adapter
    from quant.trade.brokers.ccxt.config import CCXT_PRESETS

    conninfo = _local_conninfo()
    app_user_id = _env_uuid("CCXT_ITEST_USER_ID")
    cred_id = _env_int("CCXT_ITEST_CREDENTIAL_ID")
    app_id = _env_int("CCXT_ITEST_APP_ID")
    cusip = os.getenv("CCXT_ITEST_INTERNAL_CUSIP", "btcusdt.crypto")

    api_key, api_secret = resolve_api_keys(conninfo)

    inst_cache = InstrumentCache(conninfo)
    inst_cache.load_all()
    adapter = create_ccxt_adapter(
        preset=CCXT_PRESETS["bybit"],
        api_key=api_key,
        api_secret=api_secret,
        paper=paper and not bybit_demo,
        inst_cache=inst_cache,
        demo=bybit_demo,
    )
    try:
        adapter.connect()
        adapter.gateway.validate_credentials()
        vendor = adapter.validate_for_dry_run(cusip, app_id)
        qty = adapter.get_position_qty(vendor)
        balance = adapter.gateway.exchange.fetch_balance()
        usdt = balance.get("USDT") or balance.get("usdt") or {}
        nav = usdt.get("total")
        if nav is None:
            total = balance.get("total") or {}
            nav = total.get("USDT") or total.get("usdt")
        print(f"[gateway] OK paper={paper} demo={bybit_demo} vendor_symbol={vendor} position_qty={qty} usdt_nav={nav}")
    finally:
        adapter.disconnect()
        inst_cache.close()


def refresh_live_data(
    caches,
    *,
    strategy_id: UUID,
    strategy_vid: int,
    conninfo: str,
) -> None:
    """Fetch fresh Yahoo/provider bars for the strategy lookback window (BT cache)."""
    import json

    from quant.queue.repo import BtQueueRepo
    from quant.strategy.backtest_service import fetch_df
    from quant.strategy.live_service import _default_data_source, _resolve_config_and_params
    from quant.strategy.performance import live_date_range

    bt = BtQueueRepo(conninfo, user_id="bybit_local_testnet")
    rows = bt.sp_get_strategy(strategy_id, strategy_vid)
    if not rows:
        raise SystemExit(f"Strategy {strategy_id} v{strategy_vid} not found")
    row = rows[0]
    config_json = row["config_json"]
    if isinstance(config_json, str):
        config_json = json.loads(config_json)
    result_payload = bt.fetch_result_payload(strategy_id, strategy_vid)

    ref = {
        "app": caches.refdata.get("app"),
        "indicator": caches.refdata.get("indicator"),
        "signal_type": caches.refdata.get("signal_type"),
    }
    config, window, _signal, optimize_req = _resolve_config_and_params(
        config_json, result_payload, ref,
    )
    start, end = live_date_range(window, config.trading_period)
    default_ds = (
        optimize_req.data_source
        if optimize_req is not None
        else _default_data_source(config.internal_cusip)
    )
    if optimize_req is not None:
        pairs: list[tuple[str, str | None]] = [
            (config.internal_cusip, optimize_req.data_source),
        ]
        for factor in optimize_req.factors:
            cusip = factor.symbol or config.internal_cusip
            if cusip not in {p[0] for p in pairs}:
                pairs.append((cusip, factor.data_source))
    else:
        pairs = [(config.internal_cusip, _default_data_source(config.internal_cusip))]

    print(f"[refresh] Fetching live lookback [{start}, {end}] from provider …")
    for cusip, ds_override in pairs:
        ds = ds_override or default_ds
        df = fetch_df(
            cusip,
            start,
            end,
            ds,
            ref,
            caches.instrument_cache,
            caches.backtest_cache,
            refresh=True,
        )
        last = df.index.max() if not df.empty else None
        print(f"[refresh] {cusip} via {ds}: {len(df)} rows, last={last}")


def run_dry_run(paper: bool, *, refresh_data: bool = False) -> None:
    """Full deployment dry-run orchestration (no orders)."""
    report = run_dry_run_report(paper, refresh_data=refresh_data)
    print("[dry-run] success")
    print(f"  strategy: {report.strategy_nm}")
    print(f"  vendor_symbol: {report.vendor_symbol}")
    print(f"  signal: {report.signal} → {report.intended_side}")
    print(f"  position_qty: {report.position_qty}")
    print(f"  data_as_of: {report.data_as_of}")


def run_api_dry_run(paper: bool) -> None:
    """POST /api/v1/trade/deployments/dry-run on running local API."""
    import urllib.error
    import urllib.request

    base = os.getenv("LOCAL_API_URL", "http://127.0.0.1:8000")
    username = os.getenv("LOCAL_LOGIN_USERNAME", "alfcheun")
    password = os.getenv("LOCAL_LOGIN_PASSWORD", "")
    if not password:
        raise SystemExit(
            "Set LOCAL_LOGIN_PASSWORD to call the dry-run API, "
            "or use --dry-run (direct orchestration)"
        )

    login_body = json.dumps({"username": username, "password": password}).encode()
    login_req = urllib.request.Request(
        f"{base}/api/v1/auth/login",
        data=login_body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(login_req, timeout=30) as resp:
            cookie = resp.headers.get("Set-Cookie", "")
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"Login failed ({exc.code}): {exc.read().decode()}") from exc

    token = ""
    for part in cookie.split(";"):
        if part.strip().startswith("qs_token="):
            token = part.strip().split("=", 1)[1]
            break
    if not token:
        raise SystemExit("Login succeeded but qs_token cookie missing")

    body = {
        "strategy_id": os.environ["CCXT_ITEST_STRATEGY_ID"],
        "strategy_vid": int(os.environ["CCXT_ITEST_STRATEGY_VID"]),
        "api_credential_id": int(os.environ["CCXT_ITEST_CREDENTIAL_ID"]),
        "app_id": int(os.environ["CCXT_ITEST_APP_ID"]),
        "internal_cusip": os.getenv("CCXT_ITEST_INTERNAL_CUSIP", "btcusdt.crypto"),
        "qty": os.getenv("CCXT_ITEST_QTY", "0.01"),
        "paper": paper,
    }
    dry_req = urllib.request.Request(
        f"{base}/api/v1/trade/deployments/dry-run",
        data=json.dumps(body).encode(),
        headers={
            "Content-Type": "application/json",
            "Cookie": f"qs_token={token}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(dry_req, timeout=120) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"Dry-run failed ({exc.code}): {exc.read().decode()}") from exc

    print("[api dry-run] success")
    print(json.dumps(data, indent=2))


def check_prerequisites(conninfo: str) -> None:
    """Print local setup status before running live Bybit tests."""
    from cryptography.fernet import Fernet

    print("[check] DB_TARGET=local, USE_SSM=%s" % os.getenv("USE_SSM", "(unset)"))
    key = os.getenv("EXCHANGE_SECRETS_KEY", "")
    fernet_ok = False
    if key:
        try:
            Fernet(key.encode() if isinstance(key, str) else key)
            fernet_ok = True
        except Exception:
            print("[check] WARN: EXCHANGE_SECRETS_KEY is not a valid Fernet key — use --save after fixing")
    else:
        print("[check] WARN: EXCHANGE_SECRETS_KEY unset — dev API auto-generates ephemeral key")

    has_direct = bool(
        (os.getenv("BYBIT_TESTNET_API_KEY") or os.getenv("CCXT_ITEST_API_KEY"))
        and (os.getenv("BYBIT_TESTNET_API_SECRET") or os.getenv("CCXT_ITEST_API_SECRET"))
    )
    if has_direct:
        print("[check] Direct testnet keys found in env")
    elif fernet_ok:
        import psycopg

        with psycopg.connect(conninfo) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT api_credential_id, label FROM core_admin.api_credential
                    WHERE app_id = %s AND is_active_ind = 'Y'
                    ORDER BY api_credential_id
                    """,
                    (BYBIT_APP_ID,),
                )
                rows = cur.fetchall()
        print(f"[check] {len(rows)} Bybit credential(s) in local DB: {[r[0] for r in rows]}")
        print("[check] Use --save to re-encrypt with current EXCHANGE_SECRETS_KEY if decrypt fails")
    else:
        print("[check] Add BYBIT_TESTNET_API_KEY/SECRET to .env, then: --save --gateway --dry-run")


def run_intended_side_matrix() -> None:
    """Verify intended_side golden table (no network)."""
    print("[intended-matrix] signal × position_qty → intended_side")
    mismatches: list[str] = []
    for signal, position_qty, expected in INTENDED_SIDE_GOLDEN:
        actual = _golden_intended_side(signal, position_qty)
        ok = actual == expected
        mark = "OK" if ok else "MISMATCH"
        print(
            f"  {mark:8} signal={signal:4} position={position_qty:5} "
            f"→ {actual:4} (expected {expected})"
        )
        if not ok:
            mismatches.append(f"signal={signal} pos={position_qty}: got {actual}, want {expected}")
    if mismatches:
        raise SystemExit(f"[intended-matrix] {len(mismatches)} mismatch(es)")
    print(f"[intended-matrix] {len(INTENDED_SIDE_GOLDEN)} cases OK")


def probe_intended_with_live_position(paper: bool, *, bybit_demo: bool = False) -> dict:
    """Connect to Bybit, read position, show intended_side for signals -1/0/1."""
    from quant.data.instruments import InstrumentCache
    from quant.trade.brokers.ccxt.adapter import create_ccxt_adapter
    from quant.trade.brokers.ccxt.config import CCXT_PRESETS

    conninfo = _local_conninfo()
    app_id = _env_int("CCXT_ITEST_APP_ID")
    cusip = os.getenv("CCXT_ITEST_INTERNAL_CUSIP", "btcusdt.crypto")
    api_key, api_secret = resolve_api_keys(conninfo)

    inst_cache = InstrumentCache(conninfo)
    inst_cache.load_all()
    adapter = create_ccxt_adapter(
        preset=CCXT_PRESETS["bybit"],
        api_key=api_key,
        api_secret=api_secret,
        paper=paper and not bybit_demo,
        inst_cache=inst_cache,
        demo=bybit_demo,
    )
    try:
        adapter.connect()
        vendor = adapter.validate_for_dry_run(cusip, app_id)
        position_qty = adapter.get_position_qty(vendor)
    finally:
        adapter.disconnect()
        inst_cache.close()

    print(f"[probe-intended] vendor_symbol={vendor} position_qty={position_qty}")
    outcomes: dict[str, str] = {}
    for signal in (-1.0, 0.0, 1.0):
        side = _golden_intended_side(signal, position_qty)
        outcomes[str(signal)] = side
        print(f"  signal={signal:4} → {side}")
    return {"vendor_symbol": vendor, "position_qty": position_qty, "outcomes": outcomes}


def run_apply_signal(
    paper: bool,
    signal: float,
    qty: float,
    *,
    bybit_demo: bool = False,
    confirm: bool = False,
) -> None:
    """Preview (or, with --confirm, actually place) the order for one signal.

    Prints live position before/after so each action (BUY/SELL/HOLD/
    OPEN_SHORT/CLOSE_SHORT) can be verified against the Bybit testnet UI
    one step at a time.
    """
    from quant.data.instruments import InstrumentCache
    from quant.trade.brokers.ccxt.adapter import create_ccxt_adapter
    from quant.trade.brokers.ccxt.config import CCXT_PRESETS
    from quant.trade.models.order import IntendedAction

    conninfo = _local_conninfo()
    app_id = _env_int("CCXT_ITEST_APP_ID")
    cusip = os.getenv("CCXT_ITEST_INTERNAL_CUSIP", "btcusdt.crypto")
    api_key, api_secret = resolve_api_keys(conninfo)

    inst_cache = InstrumentCache(conninfo)
    inst_cache.load_all()
    adapter = create_ccxt_adapter(
        preset=CCXT_PRESETS["bybit"],
        api_key=api_key,
        api_secret=api_secret,
        paper=paper and not bybit_demo,
        inst_cache=inst_cache,
        demo=bybit_demo,
    )
    try:
        adapter.connect()
        vendor = adapter.validate_for_dry_run(cusip, app_id)
        position_before = adapter.get_position_qty(vendor)
        action = adapter.intended_side(signal, position_before)
        print(
            f"[apply-signal] vendor_symbol={vendor} signal={signal} "
            f"position_before={position_before} → action={action} qty={qty}"
        )
        if action is IntendedAction.HOLD:
            print("[apply-signal] no order needed (HOLD)")
            return
        if not confirm:
            print(
                f"[apply-signal] DRY (no order sent) — pass --confirm to actually "
                f"submit a {action} market order on Bybit testnet"
            )
            return
        result = adapter.apply_signal(vendor, signal, qty)
        if result is None:
            print("[apply-signal] no order needed (qty resolved to 0)")
            return
        print(
            f"[apply-signal] order result: success={result.success} "
            f"vendor_order_id={result.vendor_order_id} status={result.raw_status} "
            f"message={result.message}"
        )
        if result.success:
            print(
                f"[apply-signal] fill: side={result.side} "
                f"requested_qty={result.requested_qty} filled_qty={result.filled_qty} "
                f"avg_price={result.avg_price} fee={result.fee}"
            )
        position_after = _poll_position_change(adapter, vendor, position_before)
        print(f"[apply-signal] position_after={position_after}")
    finally:
        adapter.disconnect()
        inst_cache.close()


def _poll_position_change(
    adapter, vendor_symbol: str, position_before: float, *, attempts: int = 5, delay_s: float = 1.0
) -> float:
    """Re-fetch position until it differs from ``position_before`` or attempts run out.

    Bybit's fetch_positions can briefly lag right after a market order fills.
    """
    import time

    position = adapter.get_position_qty(vendor_symbol)
    for _ in range(attempts - 1):
        if position != position_before:
            break
        time.sleep(delay_s)
        position = adapter.get_position_qty(vendor_symbol)
    return position


def _step_db_connect(conninfo: str) -> tuple[str, dict]:
    import psycopg

    with psycopg.connect(conninfo, connect_timeout=5) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
    return "local Postgres reachable", {}


def _step_redis_connect() -> tuple[str, dict]:
    from quant.refdata.bundle import DataCaches

    redis_url = os.getenv("REDIS_URL", "redis://127.0.0.1:6379")
    caches = DataCaches(_local_conninfo(), redis_url)
    if not caches.refdata.ping():
        raise RuntimeError("Redis unreachable — run: ./scripts/appctl.sh dev start")
    return f"Redis OK ({redis_url})", {"redis_url": redis_url}


def _step_strategy_payload(conninfo: str) -> tuple[str, dict]:
    from quant.queue.repo import BtQueueRepo

    strategy_id = _env_uuid("CCXT_ITEST_STRATEGY_ID")
    strategy_vid = _env_int("CCXT_ITEST_STRATEGY_VID")
    bt = BtQueueRepo(conninfo, user_id="bybit_local_testnet")
    payload = bt.fetch_result_payload(strategy_id, strategy_vid)
    if payload is None or not payload.get("best"):
        raise RuntimeError(
            f"strategy {strategy_id} v{strategy_vid} has no BT.RESULT — run backtest first"
        )
    best = payload["best"]
    return (
        f"best params window={best.get('window')} signal={best.get('signal')}",
        {"strategy_id": str(strategy_id), "strategy_vid": strategy_vid},
    )


def _step_credential_decrypt(conninfo: str) -> tuple[str, dict]:
    api_key, _ = resolve_api_keys(conninfo)
    masked = f"{api_key[:4]}…{api_key[-4:]}" if len(api_key) >= 8 else "(short)"
    cred_id = _env_int("CCXT_ITEST_CREDENTIAL_ID")
    return f"credential_id={cred_id} key={masked}", {"api_credential_id": cred_id}


def _step_xref(conninfo: str) -> tuple[str, dict]:
    import psycopg

    with psycopg.connect(conninfo) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT px.vendor_symbol FROM inst.product_xref px
                JOIN inst.product p ON p.product_id = px.product_id
                WHERE p.internal_cusip = 'btcusdt.crypto'
                  AND px.app_id = %s AND px.transact_to_ts > now()
                """,
                (BYBIT_APP_ID,),
            )
            row = cur.fetchone()
    if not row:
        raise RuntimeError("btcusdt.crypto → Bybit xref missing (run without --no-ensure-xref)")
    return f"btcusdt.crypto → {row[0]}", {"vendor_symbol": row[0]}


def run_dry_run_report(paper: bool, *, refresh_data: bool = False):
    """Like run_dry_run but return DryRunReport for suite/JSON."""
    from quant.api.credentials.repo import ApiCredentialRepo
    from quant.api.credentials.service import CredentialService
    from quant.queue.repo import BtQueueRepo
    from quant.refdata.bundle import DataCaches
    from quant.refdata.publisher import RefDataPublisher
    from quant.schemas.dry_run import DryRunRequest
    from quant.shared.secrets_crypto import CredentialCrypto
    from quant.trade.db_repo import TradeRepo
    from quant.trade.dry_run import run_dry_run as orchestrate_dry_run
    from quant.trade.registry import build_default_registry

    conninfo = _local_conninfo()
    app_user_id = _env_uuid("CCXT_ITEST_USER_ID")
    cred_id = _env_int("CCXT_ITEST_CREDENTIAL_ID")
    app_id = _env_int("CCXT_ITEST_APP_ID")
    strategy_id = _env_uuid("CCXT_ITEST_STRATEGY_ID")
    strategy_vid = _env_int("CCXT_ITEST_STRATEGY_VID")
    cusip = os.getenv("CCXT_ITEST_INTERNAL_CUSIP", "btcusdt.crypto")
    qty = Decimal(os.getenv("CCXT_ITEST_QTY", "0.01"))

    redis_url = os.getenv("REDIS_URL", "redis://127.0.0.1:6379")
    caches = DataCaches(conninfo, redis_url)
    if not caches.refdata.ping():
        raise SystemExit("Redis unreachable — run: ./scripts/appctl.sh dev start")
    try:
        caches.refdata.get("app")
    except ValueError:
        RefDataPublisher(conninfo, redis_url).publish_all()
    caches.load_instruments(soft_fail=False)
    registry = build_default_registry(caches.refdata)

    if refresh_data:
        refresh_live_data(
            caches,
            strategy_id=strategy_id,
            strategy_vid=strategy_vid,
            conninfo=conninfo,
        )

    bt = BtQueueRepo(conninfo, user_id="bybit_local_testnet")
    repo = TradeRepo(conninfo, bt=bt, user_id="bybit_local_testnet")
    cred_repo = ApiCredentialRepo(conninfo, user_id="bybit_local_testnet")
    cred_svc = CredentialService(CredentialCrypto())

    req = DryRunRequest(
        strategy_id=strategy_id,
        strategy_vid=strategy_vid,
        api_credential_id=cred_id,
        app_id=app_id,
        internal_cusip=cusip,
        qty=qty,
        paper=paper,
    )
    return orchestrate_dry_run(
        app_user_id=app_user_id,
        req=req,
        repo=repo,
        bt=bt,
        credential_service=cred_svc,
        credential_repo=cred_repo,
        adapter_registry=registry,
        data_caches=caches,
    )


def run_suite(
    *,
    paper: bool,
    bybit_demo: bool,
    ensure_xref: bool,
    include_api: bool,
) -> SuiteReport:
    """Run all golden steps; same paths as individual flags."""
    report = SuiteReport()
    conninfo = _local_conninfo()

    # ── Local / no network ───────────────────────────────────────────────
    report.add(_run_step("intended_side_matrix", lambda: (
        _run_intended_matrix_inner(),
        {"cases": len(INTENDED_SIDE_GOLDEN)},
    )))

    report.add(_run_step("db_connect", lambda: _step_db_connect(conninfo)))

    try:
        _env_uuid("CCXT_ITEST_USER_ID")
        _env_int("CCXT_ITEST_CREDENTIAL_ID")
        _env_int("CCXT_ITEST_APP_ID")
        _env_uuid("CCXT_ITEST_STRATEGY_ID")
        _env_int("CCXT_ITEST_STRATEGY_VID")
        report.add(StepResult("env_ccxt_itest", "PASS", "CCXT_ITEST_* present"))
    except KeyError as exc:
        report.add(StepResult("env_ccxt_itest", "FAIL", f"missing {exc}"))

    report.add(_run_step("redis_connect", _step_redis_connect))

    if ensure_xref:
        ensure_bybit_xref(conninfo)
    report.add(_run_step("product_xref", lambda: _step_xref(conninfo)))

    report.add(_run_step("strategy_result_payload", lambda: _step_strategy_payload(conninfo)))

    report.add(_run_step("credential_decrypt", lambda: _step_credential_decrypt(conninfo)))

    # ── Bybit network ────────────────────────────────────────────────────
    def _diagnose():
        api_key, api_secret = resolve_api_keys(conninfo)
        diagnose_bybit_keys(api_key, api_secret)
        return "see lines above for testnet/demo/mainnet", {}

    report.add(_run_step("diagnose_keys", _diagnose))

    def _gateway():
        run_gateway(paper, bybit_demo=bybit_demo)
        return f"paper={paper} demo={bybit_demo}", {}

    report.add(_run_step("gateway", _gateway))

    def _probe():
        data = probe_intended_with_live_position(paper, bybit_demo=bybit_demo)
        live = data["outcomes"].get("1.0", "?")
        return f"position={data['position_qty']} signal=1 → {live}", data

    report.add(_run_step("probe_intended", _probe))

    def _refresh():
        redis_url = os.getenv("REDIS_URL", "redis://127.0.0.1:6379")
        from quant.refdata.bundle import DataCaches
        from quant.refdata.publisher import RefDataPublisher

        caches = DataCaches(conninfo, redis_url)
        try:
            caches.refdata.get("app")
        except ValueError:
            RefDataPublisher(conninfo, redis_url).publish_all()
        caches.load_instruments(soft_fail=False)
        refresh_live_data(
            caches,
            strategy_id=_env_uuid("CCXT_ITEST_STRATEGY_ID"),
            strategy_vid=_env_int("CCXT_ITEST_STRATEGY_VID"),
            conninfo=conninfo,
        )
        return "cache refreshed for strategy lookback", {}

    report.add(_run_step("refresh_data", _refresh))

    def _dry_run():
        dr = run_dry_run_report(paper, refresh_data=False)
        detail = f"signal={dr.signal} → {dr.intended_side} as_of={dr.data_as_of}"
        return detail, dr.model_dump(mode="json")

    report.add(_run_step("dry_run", _dry_run))

    if include_api:
        if not os.getenv("LOCAL_LOGIN_PASSWORD"):
            report.add(_skip_step("api_dry_run", "LOCAL_LOGIN_PASSWORD unset"))
        else:
            def _api():
                run_api_dry_run(paper)
                return "POST /trade/deployments/dry-run OK", {}

            report.add(_run_step("api_dry_run", _api))
    else:
        report.add(_skip_step("api_dry_run", "use --suite --with-api to include"))

    report.summary()
    return report


def _run_intended_matrix_inner() -> str:
    for signal, position_qty, expected in INTENDED_SIDE_GOLDEN:
        actual = _golden_intended_side(signal, position_qty)
        if actual != expected:
            raise RuntimeError(
                f"signal={signal} position={position_qty}: got {actual}, expected {expected}"
            )
    return f"{len(INTENDED_SIDE_GOLDEN)} golden cases"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Local Bybit golden harness — validate before changing trade code",
    )
    parser.add_argument(
        "--suite",
        action="store_true",
        help="Run full golden test matrix (recommended before code changes)",
    )
    parser.add_argument(
        "--with-api",
        action="store_true",
        help="With --suite: also run API dry-run (needs LOCAL_LOGIN_PASSWORD + dev API)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="With --suite: print JSON report to stdout",
    )
    parser.add_argument(
        "--intended-matrix",
        action="store_true",
        help="Golden table: signal × position → BUY/SELL/HOLD (no network)",
    )
    parser.add_argument(
        "--probe-intended",
        action="store_true",
        help="Live Bybit position + intended_side for signals -1/0/1",
    )
    parser.add_argument(
        "--apply-signal",
        type=float,
        default=None,
        metavar="SIGNAL",
        help=(
            "Test one action at a time (BUY/SELL/HOLD/OPEN_SHORT/CLOSE_SHORT) "
            "against live position. SIGNAL in {-1,0,1}. Preview only unless --confirm."
        ),
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="With --apply-signal: actually submit the market order (else preview only)",
    )
    parser.add_argument(
        "--qty",
        type=float,
        default=None,
        help="Order qty override for --apply-signal (default: CCXT_ITEST_QTY)",
    )
    parser.add_argument("--check", action="store_true", help="Print local setup status and exit")
    parser.add_argument(
        "--diagnose",
        action="store_true",
        help="Probe key against testnet / demo / mainnet (no DB writes)",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Use Bybit Demo Trading (api-demo) instead of testnet sandbox",
    )
    parser.add_argument("--save", action="store_true", help="Save keys from BYBIT_TESTNET_* env")
    parser.add_argument("--gateway", action="store_true", help="ccxt gateway smoke test")
    parser.add_argument(
        "--refresh-data",
        action="store_true",
        help="Refresh Yahoo/provider cache before dry-run (fixes stale cache miss)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Full dry-run orchestration")
    parser.add_argument(
        "--api-dry-run",
        action="store_true",
        help="POST /api/v1/trade/deployments/dry-run (needs LOCAL_LOGIN_PASSWORD)",
    )
    parser.add_argument(
        "--ensure-xref",
        action="store_true",
        default=True,
        help="Ensure btcusdt.crypto Bybit xref exists (default: on)",
    )
    parser.add_argument(
        "--no-ensure-xref",
        action="store_false",
        dest="ensure_xref",
        help="Skip xref seeding",
    )
    args = parser.parse_args()

    if args.check:
        check_prerequisites(_local_conninfo())
        return

    paper = os.getenv("CCXT_ITEST_PAPER", "true").lower() in ("1", "true", "yes")
    bybit_demo = args.demo or os.getenv("BYBIT_USE_DEMO", "").lower() in ("1", "true", "yes")

    if args.intended_matrix:
        run_intended_side_matrix()
        return

    conninfo = _local_conninfo()

    if args.suite:
        if args.ensure_xref:
            ensure_bybit_xref(conninfo)
        suite_report = run_suite(
            paper=paper,
            bybit_demo=bybit_demo,
            ensure_xref=False,  # already ensured above when default
            include_api=args.with_api,
        )
        if args.json:
            payload = {
                "failed": suite_report.failed,
                "results": [asdict(r) for r in suite_report.results],
            }
            print(json.dumps(payload, indent=2))
        sys.exit(1 if suite_report.failed else 0)

    if args.probe_intended:
        if args.ensure_xref:
            ensure_bybit_xref(conninfo)
        probe_intended_with_live_position(paper, bybit_demo=bybit_demo)
        return

    if args.apply_signal is not None:
        if args.ensure_xref:
            ensure_bybit_xref(conninfo)
        qty = args.qty if args.qty is not None else float(os.getenv("CCXT_ITEST_QTY", "0.01"))
        run_apply_signal(
            paper, args.apply_signal, qty, bybit_demo=bybit_demo, confirm=args.confirm
        )
        return

    if args.diagnose:
        api_key, api_secret = resolve_api_keys(conninfo)
        diagnose_bybit_keys(api_key, api_secret)
        return

    if not (
        args.save
        or args.gateway
        or args.dry_run
        or args.api_dry_run
        or args.refresh_data
    ):
        parser.error(
            "Specify --suite, --check, --intended-matrix, --probe-intended, "
            "or at least one of --save, --gateway, --dry-run, "
            "--api-dry-run, --diagnose, --refresh-data"
        )

    if args.ensure_xref:
        ensure_bybit_xref(conninfo)

    if args.save:
        app_user_id = _env_uuid("CCXT_ITEST_USER_ID")
        cred_id = save_credential(conninfo, app_user_id)
        os.environ["CCXT_ITEST_CREDENTIAL_ID"] = str(cred_id)

    if args.gateway:
        run_gateway(paper, bybit_demo=bybit_demo)

    if args.refresh_data and not args.dry_run:
        redis_url = os.getenv("REDIS_URL", "redis://127.0.0.1:6379")
        from quant.refdata.bundle import DataCaches
        from quant.refdata.publisher import RefDataPublisher

        caches = DataCaches(conninfo, redis_url)
        if not caches.refdata.ping():
            raise SystemExit("Redis unreachable — run: ./scripts/appctl.sh dev start")
        try:
            caches.refdata.get("app")
        except ValueError:
            RefDataPublisher(conninfo, redis_url).publish_all()
        caches.load_instruments(soft_fail=False)
        refresh_live_data(
            caches,
            strategy_id=_env_uuid("CCXT_ITEST_STRATEGY_ID"),
            strategy_vid=_env_int("CCXT_ITEST_STRATEGY_VID"),
            conninfo=conninfo,
        )
        return

    if args.dry_run:
        run_dry_run(paper, refresh_data=args.refresh_data)

    if args.api_dry_run:
        run_api_dry_run(paper)


if __name__ == "__main__":
    main()
