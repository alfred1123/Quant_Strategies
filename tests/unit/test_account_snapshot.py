"""Unit tests for the live account snapshot — gateway parsing and the service.

No network: ccxt is patched at the gateway boundary.
"""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from quant.trade.account import fetch_account_snapshot
from quant.trade.brokers.ccxt.config import CCXT_PRESETS
from quant.trade.brokers.ccxt.gateway import CcxtSessionConfig, CcxtTradeGateway
from quant.trade.errors import AdapterNotFoundError, TradeValidationError


def _connected_gateway(mock_ccxt, exchange):
    exchange.markets = {"BTCUSDT": {}}
    exchange.has = {"fetchCurrencies": True}
    mock_ccxt.bybit.return_value = exchange
    gw = CcxtTradeGateway(
        CcxtSessionConfig(
            api_key="k", api_secret="s", preset=CCXT_PRESETS["bybit"], paper=True
        )
    )
    gw.connect()
    return gw


class TestFetchBalances:
    @patch("quant.trade.brokers.ccxt.gateway.ccxt")
    def test_reports_free_used_and_total(self, mock_ccxt):
        exchange = MagicMock()
        exchange.fetch_balance.return_value = {
            "free": {"USDT": 900.0},
            "used": {"USDT": 100.0},
            "total": {"USDT": 1000.0},
        }
        rows = _connected_gateway(mock_ccxt, exchange).fetch_balances()

        assert rows == [{"code": "USDT", "free": 900.0, "used": 100.0, "total": 1000.0}]

    @patch("quant.trade.brokers.ccxt.gateway.ccxt")
    def test_drops_empty_currencies(self, mock_ccxt):
        """A unified account lists every asset; zeroes would bury the real row."""
        exchange = MagicMock()
        exchange.fetch_balance.return_value = {
            "free": {"USDT": 10.0, "DOGE": 0.0, "XRP": 0.0},
            "used": {"USDT": 0.0, "DOGE": 0.0, "XRP": 0.0},
            "total": {"USDT": 10.0, "DOGE": 0.0, "XRP": 0.0},
        }
        rows = _connected_gateway(mock_ccxt, exchange).fetch_balances()

        assert [r["code"] for r in rows] == ["USDT"]

    @patch("quant.trade.brokers.ccxt.gateway.ccxt")
    def test_keeps_a_currency_held_only_as_margin(self, mock_ccxt):
        """free=0 with used>0 is a real holding, not an empty row."""
        exchange = MagicMock()
        exchange.fetch_balance.return_value = {
            "free": {"USDT": 0.0},
            "used": {"USDT": 250.0},
            "total": {"USDT": 250.0},
        }
        rows = _connected_gateway(mock_ccxt, exchange).fetch_balances()

        assert len(rows) == 1 and rows[0]["used"] == 250.0

    @patch("quant.trade.brokers.ccxt.gateway.ccxt")
    def test_survives_a_missing_section(self, mock_ccxt):
        """Some exchanges omit 'used' entirely."""
        exchange = MagicMock()
        exchange.fetch_balance.return_value = {"total": {"USDT": 5.0}}
        rows = _connected_gateway(mock_ccxt, exchange).fetch_balances()

        assert rows == [{"code": "USDT", "free": None, "used": None, "total": 5.0}]


class TestFetchOpenPositions:
    @patch("quant.trade.brokers.ccxt.gateway.ccxt")
    def test_flattens_the_fields_the_ui_shows(self, mock_ccxt):
        exchange = MagicMock()
        exchange.fetch_positions.return_value = [
            {
                "symbol": "BTC/USDT:USDT",
                "contracts": 0.003,
                "side": "long",
                "entryPrice": 60000.0,
                "markPrice": 61000.0,
                "notional": 183.0,
                "unrealizedPnl": 3.0,
                "leverage": 10.0,
                "liquidationPrice": 54000.0,
                "info": {"symbol": "BTCUSDT"},
            }
        ]
        rows = _connected_gateway(mock_ccxt, exchange).fetch_open_positions()

        assert len(rows) == 1
        row = rows[0]
        assert row["symbol"] == "BTCUSDT"
        assert row["unified_symbol"] == "BTC/USDT:USDT"
        assert row["qty"] == 0.003
        assert row["unrealized_pnl"] == 3.0
        assert row["leverage"] == 10.0

    @patch("quant.trade.brokers.ccxt.gateway.ccxt")
    def test_short_is_signed_negative(self, mock_ccxt):
        exchange = MagicMock()
        exchange.fetch_positions.return_value = [
            {"symbol": "BTC/USDT:USDT", "contracts": 0.002, "side": "short", "info": {}}
        ]
        rows = _connected_gateway(mock_ccxt, exchange).fetch_open_positions()

        assert rows[0]["qty"] == -0.002

    @patch("quant.trade.brokers.ccxt.gateway.ccxt")
    def test_drops_zero_size_placeholders(self, mock_ccxt):
        """Exchanges keep rows for symbols once traded."""
        exchange = MagicMock()
        exchange.fetch_positions.return_value = [
            {"symbol": "ETH/USDT:USDT", "contracts": 0.0, "side": None, "info": {}},
            {"symbol": "BTC/USDT:USDT", "contracts": 0.001, "side": "long", "info": {}},
        ]
        rows = _connected_gateway(mock_ccxt, exchange).fetch_open_positions()

        assert [r["qty"] for r in rows] == [0.001]

    @patch("quant.trade.brokers.ccxt.gateway.ccxt")
    def test_tolerates_string_numbers_and_missing_optionals(self, mock_ccxt):
        """One absent optional field must not fail the whole snapshot."""
        exchange = MagicMock()
        exchange.fetch_positions.return_value = [
            {
                "symbol": "BTC/USDT:USDT",
                "contracts": "0.004",
                "side": "long",
                "entryPrice": "",
                "info": {"symbol": "BTCUSDT"},
            }
        ]
        rows = _connected_gateway(mock_ccxt, exchange).fetch_open_positions()

        assert rows[0]["qty"] == 0.004
        assert rows[0]["entry_price"] is None
        assert rows[0]["mark_price"] is None

    @patch("quant.trade.brokers.ccxt.gateway.ccxt")
    def test_falls_back_to_info_size(self, mock_ccxt):
        exchange = MagicMock()
        exchange.fetch_positions.return_value = [
            {"symbol": "BTC/USDT:USDT", "side": "long", "info": {"size": "0.005"}}
        ]
        rows = _connected_gateway(mock_ccxt, exchange).fetch_open_positions()

        assert rows[0]["qty"] == 0.005

    @patch("quant.trade.brokers.ccxt.gateway.ccxt")
    def test_asks_for_every_symbol_not_just_deployed_ones(self, mock_ccxt):
        """A manual trade or a leftover position is the point of this view."""
        exchange = MagicMock()
        exchange.fetch_positions.return_value = []
        _connected_gateway(mock_ccxt, exchange).fetch_open_positions()

        exchange.fetch_positions.assert_called_once_with()


def _service_args(**overrides):
    credential_repo = MagicMock()
    credential_repo.get_credential.return_value = {"app_id": 34}
    credential_service = MagicMock()
    credential_service.decrypt_credential.return_value = ("key", "secret")
    adapter = MagicMock()
    adapter.get_balances.return_value = [
        {"code": "USDT", "free": 1.0, "used": 0.0, "total": 1.0}
    ]
    adapter.get_open_positions.return_value = []
    adapter.__enter__ = MagicMock(return_value=adapter)
    adapter.__exit__ = MagicMock(return_value=False)
    registry = MagicMock()
    registry.has_adapter.return_value = True
    registry.create.return_value = adapter

    args = {
        "app_user_id": uuid4(),
        "api_credential_id": 7,
        "paper": True,
        "credential_service": credential_service,
        "credential_repo": credential_repo,
        "adapter_registry": registry,
        "data_caches": MagicMock(),
    }
    args.update(overrides)
    return args


class TestFetchAccountSnapshot:
    def test_returns_balances_and_positions(self):
        snap = fetch_account_snapshot(**_service_args())

        assert snap.api_credential_id == 7
        assert snap.balances[0].code == "USDT"
        assert snap.positions == []

    def test_app_id_comes_from_the_credential_not_the_caller(self):
        """Otherwise a client could pair one exchange's keys with another's adapter."""
        args = _service_args()
        args["credential_repo"].get_credential.return_value = {"app_id": 99}

        snap = fetch_account_snapshot(**args)

        assert snap.app_id == 99
        assert args["adapter_registry"].create.call_args.args[0] == 99

    def test_unknown_credential_is_404(self):
        args = _service_args()
        args["credential_repo"].get_credential.return_value = None

        with pytest.raises(TradeValidationError) as exc:
            fetch_account_snapshot(**args)
        assert exc.value.status_code == 404

    def test_credential_owned_by_someone_else_is_404(self):
        """decrypt_credential is the owner check; None means not yours."""
        args = _service_args()
        args["credential_service"].decrypt_credential.return_value = None

        with pytest.raises(TradeValidationError) as exc:
            fetch_account_snapshot(**args)
        assert exc.value.status_code == 404

    def test_missing_adapter_raises(self):
        args = _service_args()
        args["adapter_registry"].has_adapter.return_value = False

        with pytest.raises(AdapterNotFoundError):
            fetch_account_snapshot(**args)

    @pytest.mark.parametrize("paper", [True, False])
    def test_paper_flag_reaches_the_adapter_and_the_report(self, paper):
        """The same credential addresses two accounts holding different money."""
        args = _service_args(paper=paper)

        snap = fetch_account_snapshot(**args)

        assert snap.paper is paper
        assert args["adapter_registry"].create.call_args.kwargs["paper"] is paper

    def test_session_is_closed(self):
        args = _service_args()
        fetch_account_snapshot(**args)

        args["adapter_registry"].create.return_value.__exit__.assert_called_once()

    def test_places_no_orders(self):
        """Read-only is the whole safety argument for this endpoint."""
        args = _service_args()
        fetch_account_snapshot(**args)

        adapter = args["adapter_registry"].create.return_value
        adapter.place_order.assert_not_called()
        adapter.apply_signal.assert_not_called()
        adapter.execute_action.assert_not_called()
