"""Smoke tests for every object ``scripts/bybit_local_testnet.py`` constructs.

The real constructors are ``CredentialService(crypto, repo)``,
``TradeRepo(..., credentials=, refdata=)``, and ``AdapterRegistry.create``
from ``build_default_registry``. That factory passes the Bybit preset and
``confirm_delays_s`` from ``RedisRefData.setting_floats``. A later signature
change fails here instead of at the next manual harness run.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from cryptography.fernet import Fernet

from quant.api.credentials.repo import ApiCredentialRepo
from quant.api.credentials.service import CredentialService
from quant.shared.secrets_crypto import CredentialCrypto
from quant.trade.brokers.ccxt.adapter import CcxtTradeAdapter
from quant.trade.db_repo import TradeRepo
from quant.trade.registry import AdapterRegistry
from scripts.bybit_local_testnet import (
    BYBIT_APP_ID,
    probe_intended_with_live_position,
    resolve_api_keys,
    run_apply_signal,
    run_dry_run_report,
    run_gateway,
    run_snapshot,
    save_credential,
)
from tests.conftest import StubRefData

USER = UUID("00000000-0000-0000-0000-000000000001")
STRATEGY = UUID("00000000-0000-0000-0000-000000000002")
FERNET_KEY = Fernet.generate_key().decode()
CONN = "host=127.0.0.1 port=1 dbname=none user=none password=x sslmode=disable"

_DIRECT_KEY_ENV = (
    "BYBIT_TESTNET_API_KEY",
    "BYBIT_API_KEY",
    "CCXT_ITEST_API_KEY",
    "BYBIT_TESTNET_API_SECRET",
    "BYBIT_SECRET_KEY",
    "CCXT_ITEST_API_SECRET",
)


@pytest.fixture
def db_env(monkeypatch):
    """Env-key aliases absent, so resolve_api_keys takes the database path."""
    for name in _DIRECT_KEY_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("EXCHANGE_SECRETS_KEY", FERNET_KEY)
    monkeypatch.setenv("CCXT_ITEST_USER_ID", str(USER))
    monkeypatch.setenv("CCXT_ITEST_CREDENTIAL_ID", "7")
    monkeypatch.setenv("CCXT_ITEST_APP_ID", str(BYBIT_APP_ID))
    monkeypatch.setenv("CCXT_ITEST_STRATEGY_ID", str(STRATEGY))
    monkeypatch.setenv("CCXT_ITEST_STRATEGY_VID", "3")
    monkeypatch.setenv("CCXT_ITEST_INTERNAL_CUSIP", "btcusdt.crypto")
    monkeypatch.setenv("CCXT_ITEST_QTY", "0.01")
    monkeypatch.setenv("QUANTDB_CONNINFO", CONN)


def _row(api_key: str, api_secret: str) -> dict:
    crypto = CredentialCrypto(FERNET_KEY)
    return {
        "api_key_ciphertext": crypto.encrypt(api_key),
        "api_secret_ciphertext": crypto.encrypt(api_secret),
    }


def _patch_get(monkeypatch, row):
    def get_credential(self, app_user_id, api_credential_id):
        assert self.user_id == "bybit_local_testnet"
        assert self._conninfo == CONN
        assert app_user_id == USER
        assert api_credential_id == 7
        return row

    monkeypatch.setattr(ApiCredentialRepo, "get_credential", get_credential)


def test_db_key_path_decrypts_through_credential_service(db_env, monkeypatch):
    _patch_get(monkeypatch, _row("bybit-key-1234", "bybit-secret-5678"))
    assert resolve_api_keys(CONN) == ("bybit-key-1234", "bybit-secret-5678")


def test_missing_credential_row_exits(db_env, monkeypatch):
    _patch_get(monkeypatch, None)
    with pytest.raises(SystemExit, match="Cannot decrypt credential 7"):
        resolve_api_keys(CONN)


def test_empty_decrypted_key_exits(db_env, monkeypatch):
    _patch_get(monkeypatch, _row("", ""))
    with pytest.raises(SystemExit, match="empty"):
        resolve_api_keys(CONN)


def test_env_keys_skip_the_database(db_env, monkeypatch):
    def get_credential(self, app_user_id, api_credential_id):
        raise AssertionError("env keys must not open the credential repo")

    monkeypatch.setattr(ApiCredentialRepo, "get_credential", get_credential)
    monkeypatch.setenv("BYBIT_TESTNET_API_KEY", "  env-key  ")
    monkeypatch.setenv("BYBIT_TESTNET_API_SECRET", "  env-secret  ")
    assert resolve_api_keys(CONN) == ("env-key", "env-secret")


def test_one_env_key_still_reads_the_database(db_env, monkeypatch):
    monkeypatch.setenv("BYBIT_API_KEY", "only-the-key")
    _patch_get(monkeypatch, _row("db-key", "db-secret"))
    assert resolve_api_keys(CONN) == ("db-key", "db-secret")


def test_save_credential_encrypts_through_the_service(db_env, monkeypatch):
    monkeypatch.delenv("CCXT_ITEST_APP_ID", raising=False)
    monkeypatch.setenv("BYBIT_TESTNET_API_KEY", "save-key")
    monkeypatch.setenv("BYBIT_TESTNET_API_SECRET", "save-secret")
    seen = {}

    def insert_credential(self, **kwargs):
        seen["user_id"] = self.user_id
        seen["conninfo"] = self._conninfo
        seen.update(kwargs)
        return (11, 2)

    monkeypatch.setattr(ApiCredentialRepo, "insert_credential", insert_credential)
    assert save_credential(CONN, USER) == 11
    crypto = CredentialCrypto(FERNET_KEY)
    assert crypto.decrypt(seen["api_key_ciphertext"]) == "save-key"
    assert crypto.decrypt(seen["api_secret_ciphertext"]) == "save-secret"
    assert seen["app_user_id"] == USER
    assert seen["app_id"] == BYBIT_APP_ID
    assert seen["label"] == "Bybit testnet (local script)"
    assert seen["user_id"] == "bybit_local_testnet"
    assert seen["conninfo"] == CONN


@pytest.mark.parametrize(
    ("api_key", "api_secret"),
    [("", ""), ("save-key", "   "), ("   ", "save-secret")],
)
def test_save_credential_rejects_blank_keys(db_env, monkeypatch, api_key, api_secret):
    monkeypatch.setenv("BYBIT_TESTNET_API_KEY", api_key)
    monkeypatch.setenv("BYBIT_TESTNET_API_SECRET", api_secret)
    with pytest.raises(SystemExit, match="BYBIT_TESTNET_API_KEY"):
        save_credential(CONN, USER)


def test_snapshot_service_owns_the_repo(db_env, monkeypatch):
    caches = MagicMock()
    monkeypatch.setattr(
        "scripts.bybit_local_testnet._load_caches", lambda conninfo: caches
    )
    captured = {}

    def fetch(**kwargs):
        captured.update(kwargs)
        snap = MagicMock()
        snap.model_dump.return_value = {
            "api_credential_id": kwargs["api_credential_id"],
            "app_id": BYBIT_APP_ID,
            "paper": kwargs["paper"],
            "balances": [],
            "positions": [],
        }
        return snap

    monkeypatch.setattr("quant.trade.account.fetch_account_snapshot", fetch)
    run_snapshot(True)
    svc = captured["credential_service"]
    assert isinstance(svc, CredentialService)
    assert isinstance(svc._repo, ApiCredentialRepo)
    assert svc._repo.user_id == "bybit_local_testnet"
    assert svc._repo._conninfo == CONN
    assert "credential_repo" not in captured
    assert captured["app_user_id"] == USER
    assert captured["api_credential_id"] == 7
    assert captured["paper"] is True
    assert captured["data_caches"] is caches


class _BybitRefData(StubRefData):
    """Catalog the harness reads: a Bybit ``APP`` row and a delay schedule.

    ``build_default_registry`` registers a factory only for an ``APP`` name it
    can resolve. The delay value is one the script cannot have copied.
    """

    def get(self, table: str) -> list[dict]:
        if table == "app":
            return [
                {
                    "app_id": BYBIT_APP_ID,
                    "name": "bybit",
                    "display_name": "Bybit",
                    "is_broker_ind": "Y",
                }
            ]
        return super().get(table)

    def get_config(self, table: str) -> list[dict]:
        if table == "setting":
            rows = super().get_config(table)
            return [
                {**row, "setting_value": "9.5,8.5"}
                if row["setting_nm"] == "fill_confirm_delays_s"
                else row
                for row in rows
            ]
        return super().get_config(table)


class _Stop(Exception):
    """Raised from ``connect`` once the real adapter exists."""


def test_dry_run_builds_trade_repo_and_credential_service(db_env, monkeypatch):
    refdata = StubRefData()
    caches = SimpleNamespace(refdata=refdata)
    monkeypatch.setattr(
        "scripts.bybit_local_testnet._load_caches", lambda conninfo: caches
    )
    captured = {}

    def run(**kwargs):
        captured.update(kwargs)
        return "report"

    monkeypatch.setattr("quant.trade.dry_run.run_dry_run", run)
    assert run_dry_run_report(False) == "report"
    svc = captured["credential_service"]
    assert isinstance(svc, CredentialService)
    assert isinstance(captured["repo"], TradeRepo)
    assert captured["repo"]._credentials is svc._repo
    assert captured["repo"]._refdata is refdata
    assert isinstance(svc._repo, ApiCredentialRepo)
    assert svc._repo.user_id == "bybit_local_testnet"
    assert "credential_repo" not in captured
    assert isinstance(captured["adapter_registry"], AdapterRegistry)
    assert captured["bt"] is captured["repo"]._bt
    assert captured["data_caches"] is caches
    assert captured["app_user_id"] == USER
    assert captured["req"].paper is False
    assert captured["req"].api_credential_id == 7
    assert captured["req"].strategy_vid == 3


@pytest.mark.parametrize(
    "invoke",
    [
        pytest.param(lambda: run_gateway(True), id="gateway"),
        pytest.param(lambda: probe_intended_with_live_position(False), id="probe"),
        pytest.param(
            lambda: run_apply_signal(True, 1.0, 0.01, confirm=False), id="apply"
        ),
    ],
)
def test_adapter_sites_build_through_registry(db_env, monkeypatch, invoke):
    refdata = _BybitRefData()
    inst = object()
    caches = SimpleNamespace(refdata=refdata, instrument_cache=inst)
    monkeypatch.setenv("BYBIT_TESTNET_API_KEY", "k")
    monkeypatch.setenv("BYBIT_TESTNET_API_SECRET", "s")
    monkeypatch.setattr(
        "scripts.bybit_local_testnet._load_caches", lambda conninfo: caches
    )
    built: dict = {}
    real_create = AdapterRegistry.create

    def create(self, app_id, **kwargs):
        adapter = real_create(self, app_id, **kwargs)
        built["app_id"] = app_id
        built["kwargs"] = kwargs
        built["adapter"] = adapter
        return adapter

    def connect(self):
        raise _Stop()

    monkeypatch.setattr(AdapterRegistry, "create", create)
    monkeypatch.setattr(
        "quant.trade.brokers.ccxt.adapter.CcxtTradeAdapter.connect", connect
    )
    with pytest.raises(_Stop):
        invoke()
    assert "adapter" in built, "script did not call AdapterRegistry.create"
    adapter = built["adapter"]
    assert built["app_id"] == BYBIT_APP_ID
    assert built["kwargs"]["inst_cache"] is inst
    assert "confirm_delays_s" not in built["kwargs"]
    assert isinstance(adapter, CcxtTradeAdapter)
    assert adapter._confirm_delays_s == refdata.setting_floats("fill_confirm_delays_s")
    assert adapter._confirm_delays_s == (9.5, 8.5)
    assert adapter._inst is inst
    assert adapter._session.preset.exchange_id == "bybit"
