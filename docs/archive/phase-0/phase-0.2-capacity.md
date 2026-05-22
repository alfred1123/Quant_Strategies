# Phase 0.2 — Host Capacity Snapshot

**Date:** 2026-05-20  
**Host:** `quant-server` — EC2 `i-096f85bf84852cce3` (`52.221.3.230`), **t4g.medium** (Graviton ARM, upgraded from t4g.small)  
**Safe to add +1 container (trade worker)?** **YES** on t4g.medium with normal backtest overlap; monitor with `capacity_snapshot.sh`.  
**Safe to add reconcile cron (Phase 2.2)?** **YES** — lightweight daily job; monitor peak memory during backtest queue runs.

Re-run live capture: `bash aws/scripts/capacity_snapshot.sh` on the EC2 (or via SSM). Paste output into §Live capture below.

---

## Instance budget

| Resource | t4g.small (current) | t4g.medium (upgrade) |
|----------|---------------------|----------------------|
| vCPU | 2 | 2 |
| RAM | **2 GiB** | **4 GiB** |
| Monthly (reserved ballpark) | ~$7 | ~$14 |

Source: `aws/cfn/03-compute.yml`, `aws/params/prod.json`.

---

## Current stack (Docker Compose prod)

| Service | Container | Role | Typical RAM (idle) | Peak notes |
|---------|-----------|------|-------------------|------------|
| nginx | `quant-nginx` | Static SPA + reverse proxy | ~20–40 MiB | Low |
| API | `quant-api` | FastAPI / uvicorn | ~150–350 MiB | Spikes on optimize requests |
| Queue worker | `quant-worker` | `worker_loop` + backtest subprocesses | ~150–300 MiB loop | **+500 MiB–1 GiB** per `quant.queue.worker` child during grid search |
| Redis | `quant-redis` | REFDATA + queue wake | ≤ **128 MiB** (hard cap in compose) | Stable |
| certbot | `quant-certbot` | TLS renew (prod profile) | ~20 MiB | Negligible |
| OS + Docker daemon | — | — | ~350–500 MiB | — |

**Estimated idle total:** ~0.9–1.2 GiB of 2 GiB → **~40–50% headroom at rest**.

**Estimated under load (1 queued backtest):** 1.5–2.0+ GiB → **memory pressure / swap risk** on t4g.small.

!!! note "Live numbers pending"
    SSM capture from this workspace failed (no AWS credentials). Run `aws/scripts/capacity_snapshot.sh` on the box and update §Live capture.

---

## Planned additions (plan-to-profit)

| Workload | Phase | Type | Est. RAM | CPU |
|----------|-------|------|----------|-----|
| **Trade executor** | 1.7 | Long-lived container or process (Bybit adapter, signal loop) | ~150–300 MiB idle | Low steady; bursts on rebalance |
| **Daily Sharpe reconcile** | 2.2 | Cron / one-shot container | ~50–150 MiB while running | Minutes per day |
| Manual Bybit script | — | *(If still running outside Docker)* | Unknown — **must be counted** | Check `ps aux \| grep -i bybit` on host |

---

## Headroom analysis

### +1 reconcile cron (Phase 2.2)

- Runs once daily, short-lived.
- **Verdict: YES** on current t4g.small, provided no concurrent heavy backtest.

### +1 long-lived trade worker (Phase 1.7)

- Adds a permanent Python process plus exchange I/O.
- Overlaps with queue worker when a backtest job is running → **combined RAM likely exceeds 2 GiB**.
- **Verdict: NO** on t4g.small without changes.

### Mitigations (pick one before live apply)

1. **Upgrade instance to t4g.medium** (4 GiB) — simplest; update `aws/params/prod.json` + stack update.
2. **Separate host for TRADE** — aligns with plan §6 ECR / separate-host note; decide formally in Phase 0.3.
3. **Serialize workloads** — do not run live trade executor while queue worker has an active backtest child (operational discipline only; fragile).

---

## If headroom is tight — move off the box first

| Priority | Process | Action |
|----------|---------|--------|
| 1 | Manual / legacy Bybit scripts on host | Stop or containerize; see `backup/deco/` |
| 2 | Heavy backtest queue during live trading hours | Rate-limit queue or run TRADE on separate host |
| 3 | certbot sidecar | Keep (minimal); TLS required for prod |
| 4 | Upgrade path | t4g.medium before adding trade container |

---

## Live capture

*(Paste output of `bash aws/scripts/capacity_snapshot.sh` here after running on EC2.)*

```
# pending — run on quant-server
```

---

## Recommendation summary

| Question | Answer |
|----------|--------|
| Safe to add **reconcile cron** now? | **Yes** (monitor) |
| Safe to add **trade worker** on same t4g.small? | **No** |
| Minimum change for Phase 1.7 on same host? | **t4g.medium** |
| Blocks Phase 0.3? | Feeds decision: same host only after RAM upgrade, else separate host / ECR |

---

*Phase 0.2 exit criteria met: one-page snapshot with safe-to-add Y/N and rough CPU/mem budget. Live point-in-time numbers to be pasted when SSM/SSH access is available.*
