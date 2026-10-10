"""Replace the stored series for providers the checkbox does not call.

``REFDATA.APP.REFRESH_DATASET_IND = N`` on a non-exchange app means the
drawer must not hit that vendor. This pass does, once a day, through the
same ``fetch_df`` insert a refresh uses. An exchange is skipped: its bars
already live in ``MARKET_DATA.PRICE_BAR``.

Each call is one catalog metric for one product that has a vendor symbol
for that app. The window is ``since`` through today, and the insert
replaces that whole window.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from quant.data.backtest_cache import BacktestCache

logger = logging.getLogger(__name__)


@dataclass
class FillReport:
    """How many series were stored, and which ones failed."""

    filled: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)


def scheduled_provider_apps(apps: list[dict]) -> list[dict]:
    """Non-exchange apps whose Refresh dataset checkbox is off."""
    return [
        app for app in apps
        if app.get("is_exchange_ind") != "Y" and app.get("refresh_dataset_ind") == "N"
    ]


def fill_scheduled_providers(
    refdata,
    inst_cache,
    bt_cache,
    *,
    since: date,
    today: date | None = None,
) -> FillReport:
    """Fetch and insert every scheduled provider series from *since* through *today*."""
    end = today if today is not None else datetime.now(UTC).date()
    start_s = since.isoformat()
    end_s = end.isoformat()
    report = FillReport()
    metrics = refdata.get("app_metric")

    for app in scheduled_provider_apps(refdata.get("app")):
        app_id = int(app["app_id"])
        app_metrics = [
            row for row in metrics
            if int(row["app_id"]) == app_id and row.get("metric_path")
        ]
        for xref in inst_cache.get_xrefs(app_id=app_id):
            product = inst_cache.get_product_by_id(xref["product_id"])
            if product is None:
                continue
            cusip = product["internal_cusip"]
            for metric in app_metrics:
                metric_nm = metric["metric_nm"]
                try:
                    from quant.strategy.backtest_service import fetch_df

                    fetch_df(
                        cusip, start_s, end_s, app["name"], refdata, inst_cache, bt_cache,
                        refresh=True,
                        tm_interval_id=BacktestCache.DEFAULT_TM_INTERVAL_ID,
                        metric_nm=metric_nm,
                    )
                except Exception as exc:
                    report.failed += 1
                    message = f"{app['name']} {metric_nm} {cusip}: {exc}"
                    report.errors.append(message)
                    logger.warning("scheduled provider fill failed: %s", message)
                    continue
                report.filled += 1
                logger.info(
                    "scheduled provider fill stored %s %s %s [%s, %s]",
                    app["name"], metric_nm, cusip, start_s, end_s,
                )
    return report
