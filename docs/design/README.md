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
| [Multi-strategy netting](multi-strategy-netting.md) | Recorded, not built |
| [Separate underlying & cache](separate-underlying.md) | Partial (cusip/xref only) |
| [Alternative data sources](alt-data-sources.md) | Partial (Glassnode, Nasdaq) |
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
| [AlgoDaemon bug report (2026-09-27)](2026-09-27-algodaemon-bug-report.md) | 21 items from the API review. Open high: AND-as-OR, stochastic, walk-forward warmup, cross-range promotion |

## Shipped or historical → [Archive](../archive/README.md)

Rollout playbooks, one-off bug write-ups, point-in-time capacity snapshots, and
superseded UI plans live under `docs/archive/` so this section stays short.
