"""ccxt integration — Bybit paper testnet with real DB credentials.

Golden manual harness: ``scripts/bybit_local_testnet.py --suite`` (run that first).
This pytest module mirrors gateway + dry-run paths for CI; keep in sync with the script.

All test targets come from ``CCXT_ITEST_*`` in ``.env`` (see ``.env.example``).

Run explicitly (skipped in default ``pytest tests/``):

    source env/bin/activate
    set -a && source .env && set +a
    python -m pytest tests/integration/test_ccxt_dry_run.py -v -m e2e

Uses **local Postgres** on ``127.0.0.1:5432`` — ``LOCAL_DB_*`` or ``appctl`` defaults.

Requires:
  - ``CCXT_ITEST_*`` block in ``.env`` (see ``.env.example``)
  - ``EXCHANGE_SECRETS_KEY`` (full dry-run / DB decrypt), **or**
    ``CCXT_ITEST_API_KEY`` + ``CCXT_ITEST_API_SECRET`` (gateway tests only)
  - Local Postgres, Redis (full dry-run), outbound network (Bybit testnet)
"""

from __future__ import annotations

import os
from decimal import Decimal
from uuid import UUID

import pytest

pytestmark = pytest.mark.e2e

_REQUIRED_ENV = (
    "CCXT_ITEST_USER_ID",
    "CCXT_ITEST_CREDENTIAL_ID",
    "CCXT_ITEST_APP_ID",
    "CCXT_ITEST_INTERNAL_CUSIP",
    "CCXT_ITEST_STRATEGY_ID",
    "CCXT_ITEST_STRATEGY_VID",
)


@pytest.fixture(scope="module", autouse=True)
def _load_dotenv():
    from dotenv import load_dotenv

    load_dotenv()


@pytest.fixture(scope="module", autouse=True)
def _require_itest_env():
    missing = [name for name in _REQUIRED_ENV if not os.getenv(name)]
    if missing:
        pytest.skip(
            "Missing .env entries: "
            + ", ".join(missing)
            + " — see .env.example (ccxt integration tests)"
        )


def _env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        pytest.skip(f"{name} not set in .env")
    return value


def _local_db_conninfo() -> str:
    """Local dev Postgres — mirrors ``scripts/appctl.sh`` ``DB_TARGET=local``."""
    host = os.getenv("LOCAL_DB_HOST", "127.0.0.1")
    port = os.getenv("LOCAL_DB_PORT", "5432")
    name = os.getenv("LOCAL_DB_NAME", "quantdb")
    user = os.getenv("LOCAL_DB_USER", "quant_admin")
    password = os.getenv("LOCAL_DB_PASSWORD", "LetsGetRich888")
    return (
        f"host={host} port={port} dbname={name} user={user} "
        f"password={password} sslmode=disable connect_timeout=5"
    )


@pytest.fixture(scope="module")
def conninfo():
    import psycopg

    info = _local_db_conninfo()
    try:
        with psycopg.connect(info, connect_timeout=5):
            pass
        return info
    except Exception as exc:
        pytest.skip(f"local DB not reachable ({info.split('password=')[0]}…): {exc}")


@pytest.fixture(scope="module")
def require_secrets_key():
    if (
        (os.getenv("BYBIT_TESTNET_API_KEY") and os.getenv("BYBIT_TESTNET_API_SECRET"))
        or (os.getenv("CCXT_ITEST_API_KEY") and os.getenv("CCXT_ITEST_API_SECRET"))
    ):
        return
    if not os.getenv("EXCHANGE_SECRETS_KEY"):
        pytest.skip(
            "Set EXCHANGE_SECRETS_KEY (DB decrypt) or "
            "CCXT_ITEST_API_KEY + CCXT_ITEST_API_SECRET in .env"
        )


@pytest.fixture(scope="module")
def itest_params():
    paper_raw = os.getenv("CCXT_ITEST_PAPER", "true").lower()
    return {
        "app_user_id": UUID(_env("CCXT_ITEST_USER_ID")),
        "api_credential_id": int(_env("CCXT_ITEST_CREDENTIAL_ID")),
        "app_id": int(_env("CCXT_ITEST_APP_ID")),
        "internal_cusip": _env("CCXT_ITEST_INTERNAL_CUSIP"),
        "strategy_id": UUID(_env("CCXT_ITEST_STRATEGY_ID")),
        "strategy_vid": int(_env("CCXT_ITEST_STRATEGY_VID")),
        "qty": Decimal(os.getenv("CCXT_ITEST_QTY", "0.01")),
        "paper": paper_raw in ("1", "true", "yes"),
    }


@pytest.fixture(scope="module")
def paper_api_keys(conninfo, require_secrets_key, itest_params):
    direct_key = os.getenv("BYBIT_TESTNET_API_KEY") or os.getenv("CCXT_ITEST_API_KEY")
    direct_secret = (
        os.getenv("BYBIT_TESTNET_API_SECRET") or os.getenv("CCXT_ITEST_API_SECRET")
    )
    if direct_key and direct_secret:
        return direct_key, direct_secret

    from quant.api.credentials.repo import ApiCredentialRepo
    from quant.api.credentials.service import CredentialService
    from quant.shared.secrets_crypto import CredentialCrypto

    repo = ApiCredentialRepo(conninfo, user_id="pytest")
    svc = CredentialService(CredentialCrypto())
    keys = svc.decrypt_credential(
        repo,
        itest_params["app_user_id"],
        itest_params["api_credential_id"],
    )
    if keys is None:
        pytest.skip("paper API credential not found for CCXT_ITEST_USER_ID")
    api_key, api_secret = keys
    if not api_key or not api_secret:
        pytest.skip("decrypted paper credentials are empty")
    return api_key, api_secret


def _usdt_total_from_balance(balance: dict) -> float | None:
    """Best-effort USDT total from ccxt normalized balance (may be absent on empty testnet)."""
    usdt = balance.get("USDT") or balance.get("usdt")
    if isinstance(usdt, dict):
        raw = usdt.get("total")
        if raw is not None:
            return float(raw)
    for bucket in ("total", "free", "used"):
        nested = balance.get(bucket)
        if isinstance(nested, dict):
            raw = nested.get("USDT") if nested.get("USDT") is not None else nested.get("usdt")
            if raw is not None:
                return float(raw)
    return None


@pytest.fixture(scope="module")
def inst_cache(conninfo):
    from quant.data.instruments import InstrumentCache

    cache = InstrumentCache(conninfo)
    cache.load_all()
    yield cache
    cache.close()


@pytest.fixture(scope="module")
def bybit_adapter(paper_api_keys, inst_cache, itest_params):
    from quant.trade.brokers.ccxt.adapter import create_ccxt_adapter
    from quant.trade.brokers.ccxt.config import CCXT_PRESETS

    api_key, api_secret = paper_api_keys
    adapter = create_ccxt_adapter(
        preset=CCXT_PRESETS["bybit"],
        api_key=api_key,
        api_secret=api_secret,
        paper=itest_params["paper"],
        inst_cache=inst_cache,
    )
    adapter.connect()
    yield adapter
    adapter.disconnect()


class TestCcxtBybitPaperGateway:
    """ccxt gateway against Bybit testnet — no orders."""

    def test_validate_credentials(self, bybit_adapter):
        bybit_adapter.gateway.validate_credentials()
        health = bybit_adapter.health()
        assert health.connected is True

    def test_resolve_symbol_and_market(self, bybit_adapter, itest_params):
        vendor_symbol = bybit_adapter.validate_for_dry_run(
            itest_params["internal_cusip"],
            itest_params["app_id"],
        )
        assert vendor_symbol
        assert bybit_adapter.gateway.market_exists(vendor_symbol)

    def test_fetch_position_qty_is_numeric(self, bybit_adapter, itest_params):
        vendor_symbol = bybit_adapter._require_vendor_symbol(
            itest_params["internal_cusip"],
            itest_params["app_id"],
        )
        qty = bybit_adapter.get_position_qty(vendor_symbol)
        assert isinstance(qty, float)
        assert qty >= 0.0

    def test_fetch_balance_usdt_total(self, bybit_adapter):
        """fetch_balance succeeds; USDT NAV when present (empty testnet may omit USDT)."""
        balance = bybit_adapter.gateway.exchange.fetch_balance()
        assert isinstance(balance, dict)
        assert "info" in balance, f"unexpected balance shape: {list(balance.keys())[:10]}"

        nav = _usdt_total_from_balance(balance)
        if nav is None:
            pytest.skip(
                "Bybit testnet wallet has no USDT entry — fund testnet or ignore NAV; "
                "fetch_balance still validated via test_validate_credentials"
            )
        assert nav >= 0.0


@pytest.fixture(scope="module")
def data_caches(conninfo):
    from quant.refdata.bundle import DataCaches
    from quant.refdata.publisher import RefDataPublisher

    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    caches = DataCaches(conninfo, redis_url)
    try:
        if not caches.refdata.ping():
            pytest.skip("Redis unreachable — required for deployment dry-run")
        try:
            caches.refdata.get("app")
        except ValueError:
            RefDataPublisher(conninfo, redis_url).publish_all()
    except Exception as exc:
        pytest.skip(f"Redis/REFDATA unavailable: {exc}")

    caches.load_instruments(soft_fail=False)
    return caches


@pytest.fixture(scope="module")
def adapter_registry(data_caches):
    from quant.trade.registry import build_default_registry

    return build_default_registry(data_caches.refdata)


class TestCcxtDeploymentDryRun:
    """Full ``run_dry_run`` — live position + Bybit paper + xref validation."""

    @pytest.fixture(autouse=True)
    def _require_db_secrets_key(self):
        if not os.getenv("EXCHANGE_SECRETS_KEY"):
            pytest.skip(
                "EXCHANGE_SECRETS_KEY required in .env for full dry-run"
            )

    def test_end_to_end(self, conninfo, itest_params, data_caches, adapter_registry):
        import sys
        from pathlib import Path

        from quant.api.credentials.repo import ApiCredentialRepo
        from quant.api.credentials.service import CredentialService
        from quant.queue.repo import BtQueueRepo
        from quant.schemas.dry_run import DryRunRequest
        from quant.shared.secrets_crypto import CredentialCrypto
        from quant.trade.db_repo import TradeRepo
        from quant.trade.dry_run import run_dry_run

        root = Path(__file__).resolve().parents[1]
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from scripts.bybit_local_testnet import refresh_live_data

        params = itest_params
        bt = BtQueueRepo(conninfo, user_id="pytest")
        payload = bt.fetch_result_payload(params["strategy_id"], params["strategy_vid"])
        if payload is None or not payload.get("best"):
            pytest.skip("strategy has no BT.RESULT payload — run backtest first")

        refresh_live_data(
            data_caches,
            strategy_id=params["strategy_id"],
            strategy_vid=params["strategy_vid"],
            conninfo=conninfo,
        )

        repo = TradeRepo(conninfo, bt=bt, user_id="pytest")
        cred_repo = ApiCredentialRepo(conninfo, user_id="pytest")
        cred_svc = CredentialService(CredentialCrypto())

        req = DryRunRequest(
            strategy_id=params["strategy_id"],
            strategy_vid=params["strategy_vid"],
            api_credential_id=params["api_credential_id"],
            app_id=params["app_id"],
            internal_cusip=params["internal_cusip"],
            qty=params["qty"],
            paper=params["paper"],
        )

        report = run_dry_run(
            app_user_id=params["app_user_id"],
            req=req,
            repo=repo,
            bt=bt,
            credential_service=cred_svc,
            credential_repo=cred_repo,
            adapter_registry=adapter_registry,
            data_caches=data_caches,
        )

        assert report.paper is True
        assert report.app_id == params["app_id"]
        assert report.internal_cusip == params["internal_cusip"]
        assert report.vendor_symbol
        assert report.signal in (-1.0, 0.0, 1.0)
        assert report.intended_side in ("BUY", "SELL", "HOLD")
        assert report.data_as_of
        assert isinstance(report.position_qty, float)
