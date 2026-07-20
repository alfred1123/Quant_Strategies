"""Best-effort outbound alerts — Slack first; Telegram later (Phase 2.4)."""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from uuid import UUID

import requests

logger = logging.getLogger(__name__)

_ENV_SLACK_WEBHOOK = "SLACK_WEBHOOK_URL"


class Notifier(ABC):
    """Fire-and-forget alert sink — failures must never crash callers."""

    @abstractmethod
    def send(self, message: str) -> None: ...

    @classmethod
    def from_env(cls) -> "Notifier":
        """Slack when ``SLACK_WEBHOOK_URL`` is set; log-only fallback otherwise."""
        url = os.getenv(_ENV_SLACK_WEBHOOK, "").strip()
        if url:
            return SlackNotifier(url)
        return LoggingNotifier()


class LoggingNotifier(Notifier):
    """Fallback when no webhook is configured — preserves the alert text in logs."""

    def send(self, message: str) -> None:
        logger.error("ALERT (notifier not configured): %s", message)


class SlackNotifier(Notifier):
    """Post a plain-text message to a Slack Incoming Webhook."""

    def __init__(self, webhook_url: str, *, timeout_s: float = 5.0) -> None:
        self._webhook_url = webhook_url
        self._timeout_s = timeout_s

    def send(self, message: str) -> None:
        try:
            resp = requests.post(
                self._webhook_url,
                json={"text": message},
                timeout=self._timeout_s,
            )
            resp.raise_for_status()
        except Exception:
            logger.warning("Slack alert failed to send", exc_info=True)


class TradeAlertFormatter:
    """Format ops alerts for live-trade failures (presentation layer)."""

    def title_for_apply_failure(self, *, is_permanent: bool) -> str:
        if is_permanent:
            return "Live apply failed (permanent rejection)"
        return "Live apply failed after retries — manual reconciliation required"

    def format_apply_failure(
        self,
        *,
        title: str,
        deployment_id: UUID,
        strategy_id: UUID,
        strategy_vid: int,
        symbol: str,
        signal: float,
        action: str,
        qty: float,
        paper: bool,
        attempt_count: int,
        max_attempts: int,
        last_message: str,
        vendor_order_ids: list[str],
    ) -> str:
        """Human-readable ops alert — enough to reconcile on the exchange UI."""
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        mode = "paper" if paper else "live"
        ids = ", ".join(vendor_order_ids) if vendor_order_ids else "(none)"
        return (
            f"*{title}*\n"
            f"• time: `{ts}`\n"
            f"• deployment: `{deployment_id}` ({mode})\n"
            f"• strategy: `{strategy_id}` v{strategy_vid}\n"
            f"• symbol: `{symbol}` signal={signal} action={action} qty={qty}\n"
            f"• attempts: {attempt_count}/{max_attempts}\n"
            f"• vendor_order_ids: {ids}\n"
            f"• last error: {last_message}"
        )
