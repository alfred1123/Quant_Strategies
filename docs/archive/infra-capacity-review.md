# Infrastructure Capacity Review — 2026-09-22

!!! note "Archived"
    Point-in-time snapshot. For live topology and alarms see [Infrastructure](../architecture/infrastructure.md) and [decision #74](../decisions.md).

**Question asked:** do we need a bigger EC2, or a separate host for the queue
worker / live trading? What else in the infrastructure should change?

**Answer:** neither. The host runs at **1.7 % CPU averaged over seven days** and
the one real load event this week — a 31-job backtest replay — used **one of the
two cores** and about seven CPU credits out of a full balance of 576. A live
capture during that batch (§2.3) puts host memory at **26 % peak, 2.6 GiB still
available, zero swap used, and no OOM kill in the machine's history**. The part
of the stack that needs attention is not capacity at all: **there are zero
CloudWatch alarms and zero SNS topics**, which is how a broken job-submission
path went unnoticed for five days ([decision #74](../decisions.md)), and the
Docker daemon has **no log rotation configured**, which is a slow disk leak on a
box with a disk-full history.

This page supersedes the capacity questions left open in the Phase 0 archive
([phase-0.2 capacity](phase-0/phase-0.2-capacity.md), [phase-0.3 topology](phase-0/phase-0.3-topology.md)), which
deferred "separate TRADE host" to "Phase 3.7 if t4g.medium proves tight". It has
not.

---

## 1. What is running

| Layer | Resource | Size | Last-30-day cost |
|---|---|---|---|
| Compute | EC2 `quant-server` `i-009ba73f3ad3ce9c6` | **t4g.medium** — 2 vCPU Graviton, 4 GiB, `unlimited` credit mode, 30 GiB gp3 | $10.18 |
| Database | Aurora Serverless v2 `quantdb-cluster` / `quantdb-instance-1` | PostgreSQL 17.9, **0.5 – 2.0 ACU** | $25.10 |
| Network | Elastic IP (public IPv4) | — | $3.60 |
| Other | EBS, data transfer | — | $1.68 |
| | | **Total** | **≈ $40.6 / month** |

On the host, one `docker compose` stack: `nginx`, `api` (FastAPI), `worker`
(`worker_loop`, `MAX_CONCURRENT_WORKERS=1`), `redis` (128 MiB cap). No service
declares a CPU or memory limit. See
[Infrastructure](../architecture/infrastructure.md) for the topology.

The database is **62 % of the bill**, and its cost is the 0.5 ACU floor running
24 h, not usage.

---

## 2. Evidence

All figures from CloudWatch, region `ap-southeast-1`. Timestamps UTC.

### 2.1 Seven-day baseline (2026-09-15 → 09-22, hourly)

| Metric | Average | Max (any hour) | Note |
|---|---|---|---|
| EC2 `CPUUtilization` | **1.7 %** | 59.9 % | Only **1 of 179 hours** averaged above 5 % |
| EC2 `CPUCreditBalance` | 576 | 576 | Full — the instance never spends what it earns |
| Aurora `ServerlessDatabaseCapacity` | **0.500 ACU** | 2.0 | At the floor; 28 hours contained a *brief* spike to the 2.0 ceiling (hourly crons, the 09-19/20 `pg_dump`, user backtests) |
| Aurora `CPUUtilization` | 22 % | 100 % | 22 % *of 0.5 ACU* — idle chatter from the hourly `price_bar_sync` / `trade_apply_tick` / `term_stale_connections` |
| Aurora `DatabaseConnections` | 3.9 | 10 | 3.9 ≈ two pools × `DB_POOL_MIN=2`; 10 under load, well under the 2 × `DB_POOL_MAX=10` ceiling |
| Aurora storage | 0.37 GiB | — | Trivial |

### 2.2 Load event — 31-backtest replay (2026-09-22 10:05 → 10:42 UTC)

`scripts/rerun_results.py` enqueued 31 grid-search jobs; the single worker
drained them in ~30 minutes (~1 min/job). This is the heaviest sustained load
the platform has seen and a fair proxy for a user submitting a batch.

| Metric (5-min buckets) | Peak avg | Peak max | Reading |
|---|---|---|---|
| EC2 `CPUUtilization` | 51.3 % | **51.8 %** | **One core saturated, one idle.** The worker is one process; 50 % of a 2-vCPU box is its ceiling by construction. |
| EC2 `CPUCreditUsage` | 4.9 / 5 min | — | t4g.medium earns 2 credits / 5 min. Net drain ≈ 3 / 5 min → balance 576 → 569 over the batch. A batch would have to run **~15 hours** to exhaust it; `unlimited` mode means it would then cost a few cents, not throttle. |
| EC2 `NetworkIn` + `Out` | ~60 MB / 5 min each | — | ≈ 200 KB/s. Not a factor. |
| Aurora `ServerlessDatabaseCapacity` | 0.56 ACU | **2.0** | Spiky: mostly at the floor, brief bursts to the ceiling at each job's bar fetch / result write. |
| Aurora `CPUUtilization` | 25.7 % | **100 %** | Same shape — short 100 % spikes, ~25 % average. The database was **not** the steady-state bottleneck; compute on one core was. |
| Aurora `FreeableMemory` | 2.5 GB | — | No pressure. |

Memory during this batch is covered by §2.3 — it was not visible in CloudWatch,
but `sysstat` had been recording it on the host all along.

### 2.3 Live host capture (2026-09-22 11:05 UTC, one backtest child running)

`bash aws/scripts/capacity_snapshot.sh` via SSM, plus `sar` history. This is the
"live capture" that Phase 0.2 left pending.

**Host**

| Property | Value |
|---|---|
| OS / kernel | Amazon Linux 2023.12.20260909, `6.18.44-99.149.amzn2023.aarch64` |
| CPU / RAM | 2 vCPU aarch64 / **3.7 GiB** usable |
| Docker / Compose | 25.0.16 / 5.5.1 |
| Root disk | 30 GiB gp3 — **4.4 GiB used (15 %)** |
| Uptime | 8 days |
| Swap | **none** (`swapon` empty); `vm.overcommit_memory=0`, `vm.swappiness=60` |
| CloudWatch agent | **not installed** |
| `sysstat` | **installed and collecting every 10 min** — `sar -r` / `sar -q` hold host history |
| Root crontab | empty |

**Memory — `sar -r`, 2026-09-22, spanning the batch**

| Time (UTC) | `%memused` | `kbavail` | `%commit` | Note |
|---|---|---|---|---|
| 10:00 | 8.7 % | 3.25 GiB | 55 % | pre-batch idle |
| 10:10 | 19.5 % | 2.83 GiB | 78 % | batch running |
| **10:20** | **26.3 %** | 2.56 GiB | 82 % | **peak of the day** |
| 10:30 | 19.1 % | 2.85 GiB | 72 % | between jobs |
| 10:40 | 24.0 % | 2.66 GiB | 84 % | |
| 11:00 | 25.4 % | 2.60 GiB | 87 % | one child running |

**Peak host memory use all day: 26.3 % — about 1.0 GiB of 3.7 GiB.** Swap used:
**0** throughout (`sar -S`). Load average peaked at **1.29** on 2 CPUs, i.e. a
little over one core — consistent with the CloudWatch 51 % reading.

**Per-container, cgroup v2 `memory.peak` (since the 10:27 deploy, covering
several batch jobs)**

| Container | Current | **Peak** | Limit |
|---|---|---|---|
| `quant-worker` (loop + child) | 350 MiB | **661 MiB** | `max` — unlimited |
| `quant-api` (`uvicorn --workers 2`) | 391 MiB | **414 MiB** | `max` — unlimited |
| `quant-redis` | 4.5 MiB | 8 MiB | `max` (128 MiB internal cap) |
| `quant-nginx` | 4.4 MiB | 6 MiB | `max` — unlimited |

The running child measured **239 MiB RSS** steady-state at 99.4 % CPU. The
worker container's 661 MiB peak against a ~72 MiB loop implies a child
**transiently reaching ~590 MiB** during grid search, so both numbers matter: a
child costs ~240 MiB most of the time and ~590 MiB at its worst moment.

**No OOM kill has ever occurred** — the kernel log is clean. With no swap, an
OOM would be an instant kill rather than a slowdown, which is the argument for
§4.1's `mem_limit` regardless of how much headroom exists.

---

## 3. The questions

### 3.1 Bigger EC2? — No

A t4g.large doubles RAM and the compute line (~$20/mo). Against that:

- Average CPU is 1.7 %. Peak is one core, capped there by the worker's design,
  not by the instance.
- The idle second core is already the "bigger host" — `MAX_CONCURRENT_WORKERS=2`
  roughly doubles batch throughput on the *same* instance for free. See §3.2.
- Memory peaked at **26 %** under batch load (§2.3). RAM is not the constraint.
- CPU credits are irrelevant at this duty cycle.

**Neither capacity signal points at a larger instance.** The binding limit is
2 cores, and the worker is not yet using both.

### 3.2 Three concurrent workers? — Use two

The knob is `MAX_CONCURRENT_WORKERS` (`docker-compose.yml`, default `1`);
`worker_loop` spawns one `subprocess.Popen` per claimed job up to that number,
each child a separate process with its own Postgres pool. Raising it is a
one-line compose change.

**Two is the right number on this host, and the reason is cores, not memory.**
Measured per-child cost is ~240 MiB steady / ~590 MiB peak (§2.3), so three
children worst-case lands around 2.2 GiB of 3.7 GiB — comfortable. But a
backtest child runs at ~100 % of one core for its whole life:

| `MAX_CONCURRENT_WORKERS` | Throughput | Effect |
|---|---|---|
| 1 (today) | 1× | One core busy, one idle |
| **2** | **≈ 2×** | Both cores busy — the free win |
| 3 | still ≈ 2× | Three CPU-bound processes time-slice 2 cores. No extra throughput, and `quant-api` — itself `uvicorn --workers 2` — now contends for a core when the `:05` apply tick fires |

Going past 2 needs 4 vCPU. The whole `t4g` line is 2 vCPU through `large`, so
that means `t4g.xlarge` (4 vCPU / 16 GiB) at roughly 4× the current compute
cost — unjustifiable at a 1.7 % duty cycle. Set 2, and pair it with the
`mem_limit` / `cpu_shares` guardrails in §4.1 so a second child cannot take the
API down with it.

### 3.3 Separate host for the worker or for live trading? — No

The case for a second box is isolation: a backtest batch saturating CPU at
`:05` past the hour would slow `trade_apply_tick`, and a runaway backtest child
could OOM the API. Both are real. Neither needs a second host:

| Concern | Second EC2 (t4g.small + EIP ≈ **$16/mo, +40 %**) | Same host, compose limits (**$0**) |
|---|---|---|
| Batch steals CPU from the apply tick | Solved | `cpu_shares: 512` on `worker` (API keeps default 1024). Docker only enforces shares **under contention**, which is exactly and only when it matters. With one worker process there is a free core anyway. |
| Backtest child OOMs the API | Solved | `mem_limit` on `worker` so the kernel kills the child inside its cgroup, not `quant-api`. |
| Deploy blast radius | Two SSM targets, two `git reset --hard`, two compose files, cross-host Redis | Unchanged |
| Observability | Twice as little as now (§4.2) | Unchanged |

Paying 40 % more to isolate a workload that is active **< 1 % of the time**, on
a host with a spare core, is not a good trade. The isolation we want is a cgroup
setting away.

**Revisit when any of these is true**, and not before:

- Sustained (not peak) EC2 CPU above 60 % for an hour with the compose limits in
  place — meaning both cores are genuinely busy.
- Host memory above 85 % at the trough between batches.
- More than one live-trading account whose apply latency has a hard SLA.
- The queue runs `MAX_CONCURRENT_WORKERS ≥ 3` and batch throughput is an
  explicit product goal.

Then the path is the one already sketched: a second EC2 pulling the same ECR
images with `command: worker_loop` only — or ECS, per
[Infrastructure › Future: ECS migration](../architecture/infrastructure.md#future-ecs-migration).

### 3.4 Aurora sizing? — Leave it

- **Min 0.5 ACU** is the floor. Aurora now allows min 0 (scale-to-zero), but
  the hourly crons and the two `DB_POOL_MIN=2` pools would keep it awake, so the
  pause would never engage. No saving available without restructuring the
  pools, and the pools are there for a reason
  ([Database Connections](../design/db-connections.md)).
- **Max 2.0 ACU** is hit only in sub-minute spikes. Raising it to 4 costs
  nothing at rest (you pay per ACU-second used) and would shorten the spikes;
  do it **only if** `MAX_CONCURRENT_WORKERS` goes to 2 and batches feel
  DB-bound. Not needed today.
- A provisioned `db.t4g.micro` RDS Postgres would be ~$12/mo cheaper. Same
  1 GiB as 0.5 ACU but with no burst to 4 GiB, a migration, and no Aurora
  storage/backup behaviour. **Not recommended** — $12 is not worth a database
  move.

---

## 4. What should actually change

Ordered by value per unit of effort.

### 4.1 Memory limits and a memory metric (compose + CW agent)

Not a capacity problem — a blast-radius one. Every container runs with
`memory.max = max` (§2.3), so a runaway backtest child competes with
`quant-api` for the same 3.7 GiB and, with **no swap**, the kernel's OOM killer
picks a victim by score rather than by whose fault it is. Bound the worker:

```yaml
worker:
  mem_limit: 2g          # a child dies inside its own cgroup, not the API's
  cpu_shares: 512        # api/nginx keep the default 1024
```

`mem_limit` bounds **the whole container** — the loop and every child it
spawns — not each child. At `MAX_CONCURRENT_WORKERS=2` the budget is therefore
2 × 590 MiB peak + ~72 MiB loop ≈ **1.25 GiB** measured worst case, so `2g`
carries ~750 MiB of slack and will not fire in normal operation. **It scales
with the worker count:** a third child at peak would breach 2 GiB and be OOM-killed
rather than simply queued, so `mem_limit` has to rise with any increase to
`MAX_CONCURRENT_WORKERS`. `cpu_shares` only binds **under contention**, which
is exactly when the `:05` apply tick matters and `quant-api`
(`uvicorn --workers 2`) wants a core.

**Setting up ongoing memory visibility.** The host already records it —
`sysstat` collects every 10 minutes, so `sar -r` / `sar -q` answer "what did
memory do during that batch?" retroactively, which is how §2.3 was assembled
with no agent installed:

```bash
# via SSM, no agent, no cost — history for today
aws ssm send-command --instance-ids "$INSTANCE_ID" \
  --document-name AWS-RunShellScript \
  --parameters 'commands=["sar -r","sar -q","sar -S"]' \
  --region ap-southeast-1
# yesterday and earlier: sar -r -f /var/log/sa/sa<DD>
```

That is sufficient for **investigation** and it is already running. What
`sysstat` cannot do is **alert** — its data never reaches CloudWatch, so no
alarm can read it. If we want a memory alarm (§4.2), that needs the CloudWatch
agent publishing `mem_used_percent`, which stays inside the 10-free-custom-metric
tier. Given the measured 26 % peak, memory is the *least* likely thing to page
us; install the agent for `disk_used_percent` first and take `mem_used_percent`
as a free passenger on the same config.

### 4.2 Alarms — there are none

Zero `MetricAlarms`, zero SNS topics. The `quant-scheduled-task` Lambda already
raises on any non-2xx from the API (`handler.py` re-raises `HTTPError` and
`URLError`), which makes its `Errors` metric a **free synthetic uptime check
firing four times an hour** — and it logged one error in the last seven days
that nobody saw. Wire it:

| Alarm | Metric | Threshold | Why |
|---|---|---|---|
| **API down / erroring** | `AWS/Lambda` `Errors` on `quant-scheduled-task` | ≥ 1 in 1 h | Catches 5xx, timeouts, and a dead container — the class of failure in #74 |
| Host gone | `AWS/EC2` `StatusCheckFailed` | ≥ 1 | Hardware / network |
| Host disk | `disk_used_percent` (needs CW agent) | > 80 % | The 8 → 30 GiB history says this will recur |
| DB pinned | `AWS/RDS` `ACUUtilization` | avg > 90 % for 15 min | Distinguishes a runaway query from a normal spike |
| DB connections | `AWS/RDS` `DatabaseConnections` | > 16 | 2 pools × 10 is the hard cap; 16 means something is leaking |

One SNS topic with an e-mail subscription is enough. Add these to a new
`aws/cfn/cloudwatch/alarms.yml` so they deploy with everything else; the CFN job in
`deploy.yml` already handles per-stack path detection.

### 4.3 Docker log rotation — currently none

There is **no `/etc/docker/daemon.json`** on the host, so the default
`json-file` driver runs with no `max-size` or `max-file`: container stdout grows
without bound until the container is recreated. Today it is harmless
(`/var/lib/docker/containers` is 860 KiB, root disk 15 % full) because deploys
recreate containers often enough to truncate it — but `quant-redis` has been up
8 days and a long-lived container between deploys is the leak. On a box whose
[disk-full incident](../architecture/infrastructure.md#troubleshooting-disk-full-on-deploy)
already forced an 8 → 30 GiB volume growth, this is worth closing:

```json
{ "log-driver": "json-file", "log-opts": { "max-size": "20m", "max-file": "3" } }
```

Add it to `aws/scripts/bootstrap-ec2.sh` (so a rebuilt host inherits it) and
apply once by hand; it takes effect for containers created after a
`systemctl restart docker`. Caps total container logs at ~240 MiB.

`/var/log` is 114 MiB and `logrotate.timer` is active, so the OS side is fine.

### 4.4 Close port 22

`aws/params/prod.json` still has `SshCidr: 0.0.0.0/0`. Every deploy, migration,
and recovery already goes through SSM Run Command / Session Manager, which needs
no inbound port. Set `SshCidr` to a single admin `/32` or remove the rule. Zero
cost, removes a permanently open SSH listener from a box that holds exchange
credentials in memory.

### 4.5 `MAX_CONCURRENT_WORKERS=2` — done

Applied 2026-09-22 in `docker-compose.prod.yml`, together with the §4.1
guardrails so the second child is bounded from its first run:

```yaml
worker:
  environment:
    - MAX_CONCURRENT_WORKERS=2
  mem_limit: 2g
  cpu_shares: 512
```

Roughly doubles batch throughput at no cost. Not 3 — see §3.2. If batches then
feel DB-bound, `MaxACU: 4` is the next lever (§3.4).

**Why >1 is safe despite the deferred `SP_CLAIM_NEXT`.**
`docs/env-vars.md` used to say to bump this "only after `SP_CLAIM_NEXT` becomes
atomic", which overstated the constraint by conflating *children* with
*replicas*. `WorkerLoopRepo.claim_next` is a read-then-write pair and is indeed
not atomic, but `WorkerLoop.tick` fills capacity in a **single-threaded `while`
loop**: each claim flips its row to `RUNNING` before the next read, so the
second read cannot see the first job. The race needs two `worker_loop` processes
reading the same head concurrently — which is what
[backtest-queue §0](../design/backtest-queue.md#0-v6-migration-done) defers, and we
still run one replica. `recover_stale()` keeps its single-replica assumption
untouched.

**Residual risk accepted.** Two jobs for the *same* `STRATEGY_ID` finishing at
the same instant both run promotion. `SP_UPD_PROMOTE_STRATEGY` demotes and
promotes in one transaction, so Postgres row locks serialise them and the
outcome is last-writer-wins on `IS_BEST_IND` rather than two rows marked `Y`.
Last-writer-wins is a legitimate outcome of two near-simultaneous runs, so this
is not a correctness bug — but if concurrency goes higher, add an advisory lock
per `STRATEGY_ID` the way `SP_INS_STRATEGY_VID_BY_NM` already does.

### 4.6 Do not do yet

- Second host / ECS — triggers in §3.3.
- Instance resize — no evidence; and 3 workers is the wrong reason (§3.2).
- Database engine change — §3.4.

---

## 5. Decision

Recorded as [decision #75](../decisions.md). Summary: **t4g.medium stays; no
second host; the host is over-provisioned on both CPU and memory. Raise the
worker to two — not three, because there are two cores — and bound it with
`mem_limit` / `cpu_shares`. The missing pieces are alarms, Docker log rotation,
and a closed port 22 — none of them capacity.**

### Re-running this review

```bash
# host setup, per-container memory peaks, live docker stats
aws ssm send-command --instance-ids "$INSTANCE_ID" \
  --document-name AWS-RunShellScript \
  --parameters 'commands=["cd /opt/quant && bash aws/scripts/capacity_snapshot.sh"]' \
  --region ap-southeast-1

# host memory / load history (sysstat, already collecting)
#   sar -r | sar -q | sar -S      today
#   sar -r -f /var/log/sa/sa<DD>  a previous day
```

Resolve `$INSTANCE_ID` from the `quant-compute` stack output — it changes when
the instance is replaced. CloudWatch supplies EC2 CPU / credits / network and
all Aurora metrics; `sysstat` supplies host memory; cgroup `memory.peak`
supplies the per-container high-water marks.
