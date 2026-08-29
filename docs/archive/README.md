# Archive

Completed migrations, Phase 0 signoffs, and historical design docs. Kept for reference — **not** the source of truth for current ops.

| Path | What it is | Where current truth lives |
|------|------------|---------------------------|
| [ts-migration.md](ts-migration.md) | Streamlit → React migration (done) | [React Frontend](../architecture/frontend.md) |
| [deploy-build-pipeline.md](deploy-build-pipeline.md) | ECR cutover history + implementation checklist | [Infrastructure](../architecture/infrastructure.md) |
| [backtest-api.md](backtest-api.md) | Original FastAPI concept/architecture write-up | [FastAPI Backend](../architecture/api.md) |
| [strategy-vid-versioning.md](strategy-vid-versioning.md) | `(USER_ID, STRATEGY_NM)` identity migration — audit, cleanup SQL, rollout order. Shipped in release `1.10.0` | [Database](../architecture/database.md) (`SP_INS_STRATEGY`) |
| [0.1 signoff](phase-0/phase-0.1-signoff.md) · [0.2 capacity](phase-0/phase-0.2-capacity.md) · [0.3 topology](phase-0/phase-0.3-topology.md) | Phase 0.1–0.3 signoffs (strategy health, capacity, topology) | [Plan to Profit](../design/plan-to-profit.md) |

The one-off SQL in `strategy-vid-versioning.md` (truncate, duplicate audit, merge
cleanup) has already been applied — **do not re-run it** against production.

**Current docs:** [Plan to Profit](../design/plan-to-profit.md), [Infrastructure](../architecture/infrastructure.md), [Pipeline](../architecture/pipeline.md).
