"""Live apply orchestration — signal → order → audit → ops alert."""

from __future__ import annotations

import functools
import logging
import uuid
from datetime import UTC, datetime, timedelta
from uuid import UUID

from quant.api.credentials.repo import ApiCredentialRepo
from quant.api.credentials.service import CredentialService
from quant.queue.repo import BtQueueRepo
from quant.refdata.bundle import DataCaches
from quant.schemas.apply import ApplyReport
from quant.schemas.deployments import DeploymentRow
from quant.shared.notify import Notifier, TradeAlertFormatter
from quant.strategy.live_service import (
    BarLoader,
    LiveEvaluationError,
    compute_latest_position,
)
from quant.trade.bar_source import PriceBarServiceFactory
from quant.trade.errors import AdapterNotFoundError, TradeValidationError
from quant.trade.registry import exchange_id_for_app
from quant.trade.models.order import IntendedAction, OrderResult
from quant.trade.db_repo import TradeRepo
from quant.trade.order_policy import OrderRetryExecutor, OrderRetryResult
from quant.trade.registry import AdapterRegistry

logger = logging.getLogger(__name__)

# Used only when INST.PRODUCT.CCY is not populated for the instrument.
_FALLBACK_SETTLEMENT_CCY = "USDT"


class LiveApplyOrchestrator:
    """Execute one live-apply cycle: signal → order → audit → ops alert."""

    def __init__(
        self,
        repo: TradeRepo,
        bt: BtQueueRepo,
        credential_service: CredentialService,
        credential_repo: ApiCredentialRepo,
        adapter_registry: AdapterRegistry,
        data_caches: DataCaches,
        *,
        price_bars: PriceBarServiceFactory | None = None,
        retry_executor: OrderRetryExecutor | None = None,
        alert_formatter: TradeAlertFormatter | None = None,
        notifier: Notifier | None = None,
    ) -> None:
        self._repo = repo
        self._bt = bt
        self._credential_service = credential_service
        self._credential_repo = credential_repo
        self._adapter_registry = adapter_registry
        self._data_caches = data_caches
        self._price_bars = price_bars
        self._retry_executor = retry_executor or OrderRetryExecutor()
        self._alert_formatter = alert_formatter or TradeAlertFormatter()
        self._notifier = notifier or Notifier.from_env()

    def run(
        self,
        app_user_id: UUID,
        deployment: DeploymentRow,
        user_id: str,
    ) -> ApplyReport:
        # One tick time for the whole cycle — every attempt shares this anchor
        # so the diary groups by tick, not by per-row insert time.
        tick_at = datetime.now(UTC)
        if not self._adapter_registry.has_adapter(deployment.app_id):
            raise AdapterNotFoundError(
                f"no broker adapter registered for app_id={deployment.app_id}"
            )
        keys = self._credential_service.decrypt_credential(
            self._credential_repo, app_user_id, deployment.api_credential_id
        )
        if keys is None:
            raise TradeValidationError(
                "API credential not found or cannot decrypt", status_code=404
            )

        signal, bar_source = self._compute_signal(deployment)

        adapter = self._adapter_registry.create(
            deployment.app_id,
            api_key=keys[0],
            api_secret=keys[1],
            paper=deployment.is_paper_ind == "Y",
            inst_cache=self._data_caches.instrument_cache,
        )
        with adapter:
            vendor_symbol = adapter.validate_for_dry_run(
                deployment.internal_cusip, deployment.app_id
            )
            qty = float(deployment.qty)
            outcome = self._retry_executor.execute(
                adapter, vendor_symbol, signal, qty,
            )

            self._audit_attempts(
                outcome, app_user_id=app_user_id, deployment=deployment,
                signal=signal, user_id=user_id, qty=qty, tick_at=tick_at,
            )

            result = outcome.result
            if result is None:
                return self._report(deployment, outcome, vendor_symbol, signal,
                                    bar_source=bar_source,
                                    message=outcome.no_order_message)

            if result.success:
                self._write_transaction(
                    app_user_id=app_user_id, deployment=deployment,
                    action=outcome.action, vendor_symbol=vendor_symbol,
                    result=result, user_id=user_id,
                )
            else:
                self._send_failure_alert(
                    deployment, outcome, vendor_symbol, signal, qty,
                )
            return self._report(
                deployment, outcome, vendor_symbol, signal, bar_source=bar_source
            )

    def _compute_signal(self, deployment: DeploymentRow) -> tuple[float, str]:
        """``(signal, bar_source)`` — the position and the series behind it."""
        strategy_rows = self._bt.sp_get_strategy(
            deployment.strategy_id, strategy_vid=deployment.strategy_vid
        )
        if not strategy_rows:
            raise TradeValidationError(
                f"strategy {deployment.strategy_id} v{deployment.strategy_vid} not found",
                status_code=404,
            )
        result_payload = self._bt.fetch_result_payload(
            deployment.strategy_id, deployment.strategy_vid
        )
        bar_loader, bar_source = self._resolve_signal_source(deployment)
        try:
            signal, data_as_of = compute_latest_position(
                strategy_rows[0]["config_json"],
                result_payload=result_payload,
                caches=self._data_caches,
                bar_loader=bar_loader,
            )
        except LiveEvaluationError as exc:
            raise TradeValidationError(str(exc)) from exc

        logger.info(
            "signal=%s as_of=%s source=%s for deployment %s (%s)",
            signal, data_as_of, bar_source,
            deployment.deployment_id, deployment.internal_cusip,
        )
        return signal, bar_source

    def _resolve_signal_source(
        self, deployment: DeploymentRow
    ) -> tuple[BarLoader | None, str]:
        """Pick the price series for this deployment, and name it.

        The rule is by venue, not by schedule: a live signal reads the bars of
        the exchange it executes on whenever that exchange serves market data.
        The schedule only sets the bar interval — without one the apply is
        assumed daily. The provider path survives solely for brokers with no
        market-data venue (e.g. Futu equities), where the provider series is
        the only series that exists.

        The label travels onto :class:`ApplyReport` because the two sources are
        not the same numbers — parameters fitted on provider history are being
        traded against exchange prints — and a divergence is only diagnosable
        if the input is recorded alongside the output.
        """
        venue = exchange_id_for_app(
            deployment.app_id, refdata=self._data_caches.refdata
        )
        interval_id = deployment.schedule_tm_interval_id
        if interval_id is None:
            if venue is None:
                return None, "provider"
            interval_id = self._data_caches.refdata.resolve_interval_id(
                timedelta(days=1)
            )
        if self._price_bars is None:
            raise TradeValidationError(
                f"deployment {deployment.deployment_id} needs exchange bars on "
                f"interval {interval_id} but no price bar source is configured"
            )
        # for_app refuses venue-less apps, so a loader implies a named venue.
        loader = functools.partial(
            self._price_bars.for_app(deployment.app_id).load_window,
            tm_interval_id=interval_id,
            source_app_id=deployment.app_id,
        )
        return loader, f"price_bar:{venue}"

    def _report(
        self,
        deployment: DeploymentRow,
        outcome: OrderRetryResult,
        vendor_symbol: str,
        signal: float,
        *,
        bar_source: str,
        message: str | None = None,
    ) -> ApplyReport:
        result = outcome.result
        return ApplyReport(
            bar_source=bar_source,
            deployment_id=deployment.deployment_id,
            deployment_vid=deployment.deployment_vid,
            action=outcome.action,
            vendor_symbol=vendor_symbol,
            signal=signal,
            position_qty=outcome.position_qty,
            order_success=result.success if result else None,
            vendor_order_id=result.vendor_order_id if result else None,
            filled_qty=result.filled_qty if result else None,
            avg_price=result.avg_price if result else None,
            fee=result.fee if result else None,
            message=message if message is not None else result.message,
        )

    def _audit_attempts(
        self,
        outcome: OrderRetryResult,
        *,
        app_user_id: UUID,
        deployment: DeploymentRow,
        signal: float,
        user_id: str,
        qty: float,
        tick_at: datetime,
    ) -> None:
        """Best-effort EXECUTION_EVENT row per attempt — never fails the cycle.

        ``position_qty`` is per attempt rather than per cycle: every attempt
        re-reads the book, so a partial fill between two of them shows up as a
        moving position instead of one number repeated.
        """
        for attempt in outcome.attempts:
            try:
                self._repo.sp_ins_execution_event(
                    execution_event_id=uuid.uuid4(),
                    app_user_id=app_user_id,
                    deployment_id=deployment.deployment_id,
                    deployment_vid=deployment.deployment_vid,
                    buy_sell_cd=attempt.buy_sell_cd,
                    is_success_ind=attempt.is_success_ind,
                    user_id=user_id,
                    signal_value=signal,
                    quantity=attempt.quantity(qty),
                    vendor_order_id=attempt.vendor_order_id,
                    transact_at=tick_at,
                    position_qty=attempt.position_qty,
                )
            except Exception:
                logger.exception("audit write failed — apply cycle continues")

    def _write_transaction(
        self,
        *,
        app_user_id: UUID,
        deployment: DeploymentRow,
        action: IntendedAction,
        vendor_symbol: str,
        result: OrderResult,
        user_id: str,
    ) -> None:
        """Best-effort fill row — never fails the apply cycle."""
        side = action.order_side()
        if side is None or result.filled_qty is None:
            return
        notional = None
        if result.avg_price is not None:
            notional = float(result.filled_qty) * float(result.avg_price)
        try:
            self._repo.sp_ins_transaction(
                transaction_id=uuid.uuid4(),
                app_user_id=app_user_id,
                deployment_id=deployment.deployment_id,
                app_id=deployment.app_id,
                internal_cusip=deployment.internal_cusip,
                buy_sell_cd=side.value,
                trans_ccy_cd=self._settlement_ccy(deployment.internal_cusip),
                user_id=user_id,
                vendor_symbol=vendor_symbol,
                quantity=result.filled_qty,
                price=result.avg_price,
                notional_amt=notional,
                fee_amt=result.fee,
                vendor_order_id=result.vendor_order_id,
            )
        except Exception:
            logger.exception("transaction write failed — apply cycle continues")

    def _settlement_ccy(self, internal_cusip: str) -> str:
        """Settlement currency from the instrument master (INST.PRODUCT.CCY)."""
        product = self._data_caches.instrument_cache.get_product_by_cusip(
            internal_cusip
        )
        ccy = (product or {}).get("ccy")
        if ccy:
            return ccy
        logger.warning(
            "no CCY on INST.PRODUCT for %s — falling back to %s",
            internal_cusip, _FALLBACK_SETTLEMENT_CCY,
        )
        return _FALLBACK_SETTLEMENT_CCY

    def _send_failure_alert(
        self,
        deployment: DeploymentRow,
        outcome: OrderRetryResult,
        vendor_symbol: str,
        signal: float,
        qty: float,
    ) -> None:
        assert outcome.result is not None
        title = self._alert_formatter.title_for_apply_failure(
            is_permanent=outcome.permanent_failure,
        )
        self._notifier.send(
            self._alert_formatter.format_apply_failure(
                title=title,
                deployment_id=deployment.deployment_id,
                strategy_id=deployment.strategy_id,
                strategy_vid=deployment.strategy_vid,
                symbol=vendor_symbol,
                signal=signal,
                action=outcome.action.value,
                qty=qty,
                paper=deployment.is_paper_ind == "Y",
                attempt_count=len(outcome.attempts),
                max_attempts=outcome.max_attempts,
                last_message=outcome.result.message,
                vendor_order_ids=outcome.vendor_order_ids,
            )
        )
