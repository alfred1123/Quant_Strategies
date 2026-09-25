# Archive

Completed migrations, Phase 0 signoffs, and historical design docs. Kept for reference — **not** the source of truth for current ops.

## Migrations & signoffs

| Path | What it is | Where current truth lives |
|------|------------|---------------------------|
| [ts-migration.md](ts-migration.md) | Streamlit → React migration (done) | [React Frontend](../architecture/frontend.md) |
| [deploy-build-pipeline.md](deploy-build-pipeline.md) | ECR cutover history + implementation checklist | [Infrastructure](../architecture/infrastructure.md) |
| [backtest-api.md](backtest-api.md) | Original FastAPI concept/architecture write-up | [FastAPI Backend](../architecture/api.md) |
| [strategy-vid-versioning.md](strategy-vid-versioning.md) | `(USER_ID, STRATEGY_NM)` identity migration — audit, cleanup SQL, rollout order. Shipped in release `1.10.0` | [Database](../architecture/database.md) (`SP_INS_STRATEGY`) |
| [0.1 signoff](phase-0/phase-0.1-signoff.md) · [0.2 capacity](phase-0/phase-0.2-capacity.md) · [0.3 topology](phase-0/phase-0.3-topology.md) | Phase 0.1–0.3 signoffs (strategy health, capacity, topology) | [Plan to Profit](../design/plan-to-profit.md) |

## Shipped platform designs (2026-09 cleanup)

| Path | What it is | Where current truth lives |
|------|------------|---------------------------|
| [trade-deployment-rollout.md](trade-deployment-rollout.md) | Phases 1.6–1.9 rollout (picker → apply → scheduler) | [Trade API](../design/trade-api.md), [API](../architecture/api.md), [Plan to Profit](../design/plan-to-profit.md) |
| [live-order-execution.md](live-order-execution.md) | Fill confirmation, retry, Slack alerting (Phase 1.7) | `quant/trade/live_apply.py`, [Live trading promotion](../guides/live-trading-promotion.md) |
| [backtest-speed.md](backtest-speed.md) | Optuna / exhaustive grid search optimization | [Pipeline](../architecture/pipeline.md), `quant/strategy/optimizer.py` |
| [return-compounding.md](return-compounding.md) | `cumu` compounding bug write-up (fixed) | `quant/strategy/performance.py`, [data hygiene proposal](../design/2026-09-25-backtest-data-hygiene-proposal.md) |
| [infra-capacity-review.md](infra-capacity-review.md) | Point-in-time EC2/Aurora snapshot (2026-09-22) | [Infrastructure](../architecture/infrastructure.md), [decision #75](../decisions.md) |
| [backtest-queue-json-viewer.md](backtest-queue-json-viewer.md) | Abandoned read-only JSON dialog plan | Jobs table opens [ConfigDrawer](../architecture/frontend.md) with job config instead |

The one-off SQL in `strategy-vid-versioning.md` (truncate, duplicate audit, merge
cleanup) has already been applied — **do not re-run it** against production.

**Active design index:** [Platform design](../design/README.md) · **Ops:** [Production rollout](../guides/prod-rollout.md)
