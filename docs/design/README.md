# Platform design — index

Specs and proposals for **software the platform should build**. For alpha /
market ideas see [Strategy research](../research/README.md). For how things run
today see [Architecture](../architecture/overview.md).

## Active specs (still edited)

| Doc | Status |
|-----|--------|
| [Trade API](trade-api.md) | Mostly implemented; §7 DDL is reference |
| [Scheduler, price bars & consolidation](scheduler-price-bars.md) | Phase 1.9 shipped; timing amended by decision #81 |
| [ccxt bar timezones & apply timing](ccxt-bar-timezones.md) | Living reference for bar alignment |
| [Market data capture](market-data-capture.md) | Built; subscription model |
| [ccxt trade & XREF validation](ccxt-trade-and-xref-validation.md) | Dry-run / validation path |
| [Backtest queue](backtest-queue.md) | v6 implemented — queue contract + worker |
| [Plan to profit](plan-to-profit.md) | Product roadmap (phases) |
| [Best-VID promotion](best-vid-promotion.md) | Implemented — gates + UI |
| [Scheduler & trade open questions](scheduler-trade-open-questions.md) | Open app-layer items |
| [Database connections](db-connections.md) | Current pool / gateway rules |

## Backlog (not built or partial)

| Doc | Status |
|-----|--------|
| [Jobs table detail UX](jobs-table-detail-ux.md) | Proposed |
| [Queue screen aids (2026-09-29)](2026-09-29-queue-frontend-aids.md) | Proposed — result in Config, metric tooltips, queue search, two-job compare. Frontend only |
| [Deployment performance reconcile](deployment-performance-reconcile.md) | Proposed — Phase 2.1–2.3 |
| [Multi-strategy netting](multi-strategy-netting.md) | `TRADE.INTENT` built (#90, trade `1.10.0`); order side recorded |
| [Separate underlying & cache](separate-underlying.md) | Partial (cusip/xref only) |
| [Alternative data sources](alt-data-sources.md) | Partial (Glassnode, Nasdaq) |
| [Glassnode market data](glassnode-market-data.md) | Draft — narrower `{t, v}` store; history is kept and old copies are archived out of the live table in a later pull request |
| [User isolation](user-isolation.md) | v1 partial — shared strategy pool |
| [Login & authentication](login.md) | Phase 1 done; phases 2–3 proposed |
| [Futu trading (OOP)](futu-trading.md) | Design only |
| [Frontend code audit](frontend-audit.md) | Hardening done; follow-ups open |
| [Backtest data hygiene](2026-09-25-backtest-data-hygiene-proposal.md) | Short-sample refusal adopted (#82); stale results, identity, and catalog still proposed |
| [Fractional sizing and stateful exits](2026-09-26-fractional-sizing-stateful-exits.md) | Proposed — Donchian on closes, hysteresis, weights, averaged ensemble |

## Reviews

| Doc | Status |
|-----|--------|
| [Backtest review (2026-09-25)](2026-09-25-backtest-review.md) | Open findings — measurement, promotion, and live fill |
| [Code quality review (2026-09-26)](2026-09-26-code-quality-review.md) | Open findings — scheduler replay, worker reap, and how indicators and signals are modelled |
| [AlgoDaemon bug report (2026-09-27)](2026-09-27-algodaemon-bug-report.md) | 21 items from the API review. AND-as-OR is fixed in the combiner; stored results still need flagging. Open high: stochastic, walk-forward warmup, cross-range promotion |
| [Bug verification, rounds 3–4 (2026-09-27)](2026-09-27-bug-verification-round3-4.md) | Seven follow-up items: SMA/EMA raw levels, sampled big grids, window bounds, same-close fills, duplicate versions (B24), volume limited to a raw column (B26). Hourly annualisation downgraded |
| [Long-term fixes: B1, window bounds, data columns, repeated trials (2026-09-29)](2026-09-29-long-term-fixes-b1-rangeparam-datacolumn.md) | Design items for decision. #76 is the B1 root-cause fix; window floor, data-column check and distinct-trial search proposed |
| [Dependency and OOP review (2026-09-29)](2026-09-29-dependency-review.md) | Open findings: package cycles, layer leaks, and live-trading failure paths that have no test yet |

## Shipped or historical → [Archive](../archive/README.md)

Rollout playbooks, one-off bug write-ups, point-in-time capacity snapshots, and
superseded UI plans live under `docs/archive/` so this section stays short.
