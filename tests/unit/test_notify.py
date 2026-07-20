"""Unit tests for quant.shared.notify."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import requests

from quant.shared.notify import (
    LoggingNotifier,
    Notifier,
    SlackNotifier,
    TradeAlertFormatter,
)


class TestSlackNotifier:
    @patch("quant.shared.notify.requests.post")
    def test_send_posts_json(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, text="ok")
        mock_post.return_value.raise_for_status = MagicMock()
        SlackNotifier("https://hooks.slack.com/services/T/B/X").send("hello")
        mock_post.assert_called_once_with(
            "https://hooks.slack.com/services/T/B/X",
            json={"text": "hello"},
            timeout=5.0,
        )

    @patch("quant.shared.notify.requests.post", side_effect=requests.Timeout())
    def test_send_swallows_errors(self, mock_post):
        SlackNotifier("https://hooks.slack.com/services/T/B/X").send("hello")


class TestNotifierFromEnv:
    @patch.dict("os.environ", {}, clear=True)
    def test_missing_url_uses_logging_notifier(self):
        assert isinstance(Notifier.from_env(), LoggingNotifier)

    @patch.dict("os.environ", {"SLACK_WEBHOOK_URL": "https://hooks.slack.com/x"})
    def test_configured_url_uses_slack(self):
        assert isinstance(Notifier.from_env(), SlackNotifier)


class TestTradeAlertFormatter:
    def test_permanent_title(self):
        title = TradeAlertFormatter().title_for_apply_failure(is_permanent=True)
        assert "permanent" in title.lower()

    def test_retry_exhaustion_title(self):
        title = TradeAlertFormatter().title_for_apply_failure(is_permanent=False)
        assert "manual reconciliation" in title.lower()

    def test_includes_key_fields(self):
        dep_id = uuid4()
        strat_id = uuid4()
        text = TradeAlertFormatter().format_apply_failure(
            title="Test alert",
            deployment_id=dep_id,
            strategy_id=strat_id,
            strategy_vid=2,
            symbol="BTCUSDT",
            signal=1.0,
            action="BUY",
            qty=0.01,
            paper=True,
            attempt_count=3,
            max_attempts=5,
            last_message="fill unconfirmed",
            vendor_order_ids=["oid-1", "oid-2"],
        )
        assert "Test alert" in text
        assert str(dep_id) in text
        assert "BTCUSDT" in text
        assert "oid-1" in text
        assert "fill unconfirmed" in text
