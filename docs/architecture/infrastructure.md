# Infrastructure

Infrastructure as Code for the Quant Strategies deployment.
All resources are defined as CloudFormation templates under `aws/cfn/<service>/`
and deployed via the AWS CLI.

See [System Overview](overview.md) for runtime topology and [Dev vs Prod](dev-vs-prod.md) for environment differences.

---

## Architecture

```
   Browser (Cloudflare)          EventBridge → quant-scheduled-task Lambda
            │ HTTPS :443                     │ POST /api/v1/scheduler/tick
            ▼                                ▼
 ┌─────────────────────── EC2 t4g.medium, ap-southeast-1 ───────────────────────┐
 │  nginx :443 ──► api :8000 (FastAPI)            worker (quant.queue.worker_loop)│
 │                 trade: dry-run, apply,         backtests only: claims BT.QUEUE,│
 │                 scheduled tick                 writes BT.RESULT                │
 │                   │         │                        │                        │
 │                   │         └──── redis ◄────────────┤                        │
 │                   │  EIP 52.221.3.230                 │                        │
 └───────────────────┼───────────────────────────────────┼────────────────────────┘
        keyless ccxt │ keyed ccxt                         │ VPC :5432
       (limits, bars)│ (uk route)                         ▼
            │        ▼                          ┌──────────────────────┐
            │  ┌──────────────────────────┐     │ Aurora Serverless v2 │◄── api
            │  │ squid, t4g.nano, London  │     │ PostgreSQL 17.9      │
            │  │ EIP 13.43.55.53 :3128    │     │ 0.5 – 2.0 ACU        │
            │  │ CONNECT to Bybit only    │     └──────────────────────┘
            │  └────────────┬─────────────┘
            ▼               ▼
                api.bybit.com
```

SSM Parameter Store supplies secrets (`JWT_SECRET`, `EXCHANGE_SECRETS_KEY`, DB credentials) and settings such as `CCXT_EGRESS_BYBIT` at app startup.

Only `api` talks to exchanges. It serves the SPA's trade endpoints and runs the
scheduled apply that the Lambda triggers, so every order, dry-run and key check
leaves from the `api` container. `worker` runs backtests from `BT.QUEUE` and
never opens a keyed exchange session, so an exchange or egress setting takes
effect by restarting `api` alone.

The base `docker-compose.yml` exposes nginx on **:80** (HTTP, using `nginx.dev.conf`). For HTTPS there are two overlays:

- **`docker-compose.cloudflare.yml`** — production default. Site sits behind Cloudflare (orange cloud) with a **Cloudflare Origin Certificate** terminating TLS at nginx (`nginx.cloudflare.conf`, `:443`). Wired automatically by the deploy pipeline when the `DOMAIN` GitHub variable and `/quant/prod/ORIGIN_TLS_CERT` + `ORIGIN_TLS_KEY` SSM params are present. See [HTTPS via Cloudflare](../guides/https-cloudflare.md).
- **`docker-compose.tls.yml`** — alternative for a DNS-only (grey cloud) / no-CDN setup. Swaps in `nginx.conf` and adds **:443** with Let's Encrypt (certbot).

---

## Directory layout

```
aws/
├── import-db-resources.json   ← resource mapping used during Aurora import
├── deploy.sh                  ← deploy / update all stacks
├── cfn/                       ← CloudFormation templates, one folder per service
│   ├── ecr/
│   │   └── image-repositories.yml ← ECR repos quant-app, quant-nginx
│   ├── vpc/
│   │   └── security-groups.yml    ← security groups (EC2 + RDS)
│   ├── database/
│   │   └── aurora-cluster.yml     ← Aurora PostgreSQL Serverless v2
│   ├── ec2/
│   │   ├── app-host.yml           ← EC2 + IAM role + EIP
│   │   └── uk-egress-proxy.yml    ← eu-west-2 CONNECT proxy for Bybit orders
│   └── eventbridge/
│       └── scheduled-task.yml     ← EventBridge Scheduler + scheduled-task Lambda
├── lambda/
│   └── scheduled-task/        ← Lambda handler (uploaded by deploy.sh)
├── params/
│   └── prod.json              ← parameter values for prod
├── iam/
│   ├── github-deploy-cfn-policy.json   ← CFN deploy via GitHub Actions
│   ├── github-deploy-policy.json       ← SSM Run Command deploy
│   └── github-deploy-ecr-policy.json   ← ECR push (attach before workflow step 3)
└── scripts/
    ├── bootstrap-ec2.sh     ← one-time EC2 setup
    ├── init-ssm-params.sh   ← bootstrap SSM secrets (run once)
    └── capacity_snapshot.sh ← Phase 0.2 host CPU/mem capture
```

---

## Prerequisites

1. **AWS CLI v2** installed and authenticated (`aws sso login --profile <profile>`)
2. **EC2 key pair** created in the target region (current: `tradingServerKey`)
3. **Domain name** (optional but recommended for TLS)

---

## Stacks (deployment order)

Stacks must be deployed in order due to cross-stack references. Templates live
under `aws/cfn/<service>/`, grouped by the **AWS service** that owns their
resources, so the folder says what a template creates while `params/` and
`scripts/` — kinds of file, not services — stay out of that namespace. The order
lives in `deploy.sh`'s `ORDERED` array rather than in a filename prefix.

**The deploy target is not always the stack name.** `deploy.sh` builds the stack
name as `quant-<target>` unless `STACK_SUFFIX` overrides it, and three targets
do override. CloudFormation identifies a stack **by name**: renaming one here
would not rename the deployed stack, it would create a second empty one and
orphan the live resources. So the folders were free to move and the deployed
names are frozen.

| # | Stack | Deploy target | Template | Creates |
|---|-------|---------------|----------|---------|
| 0 | `quant-ecr` | `ecr` | `cfn/ecr/image-repositories.yml` | ECR repos `quant-app`, `quant-nginx` |
| 1 | `quant-network` | `vpc` | `cfn/vpc/security-groups.yml` | EC2 SG (22/80/443), RDS SG (5432 from EC2 only) |
| 2 | `quant-database` | `database` | `cfn/database/aurora-cluster.yml` | Aurora cluster, serverless instance, DB subnet group |
| 3 | `quant-compute` | `ec2` | `cfn/ec2/app-host.yml` | EC2 instance, IAM role (SSM access), Elastic IP |
| 4 | `quant-scheduler` | `eventbridge` | `cfn/eventbridge/scheduled-task.yml` | scheduled-task Lambda, EventBridge schedule group, invoke + EC2 manage IAM |
| — | `quant-uk-egress` | `uk-egress` | `cfn/ec2/uk-egress-proxy.yml` | **eu-west-2 only** — VPC, t4g.nano squid host, Elastic IP giving Bybit orders a London source address |

---

## Deploying

### First time — bootstrap secrets

```bash
# Set up SSM parameters (prompts for DB password and JWT secret)
bash aws/scripts/init-ssm-params.sh

# Prod only — add Fernet key for exchange credentials (required for API boot)
aws ssm put-parameter --name /quant/prod/EXCHANGE_SECRETS_KEY \
  --value "$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')" \
  --type SecureString --region ap-southeast-1
```

### Deploy all stacks

```bash
# Validate templates first (no changes)
bash aws/deploy.sh all --dry-run

# Deploy everything
bash aws/deploy.sh
```

### Deploy a single stack

```bash
bash aws/deploy.sh vpc
bash aws/deploy.sh database
bash aws/deploy.sh ec2
bash aws/deploy.sh eventbridge   # normally CI; requires /quant/prod/TRADE_SERVICE_TOKEN in SSM

# The one stack in another region — its whole purpose is the London IP
AWS_REGION=eu-west-2 bash aws/deploy.sh uk-egress
```

### Updating

Re-run `bash aws/deploy.sh <stack>`. CloudFormation creates a changeset
and only modifies what changed. `--no-fail-on-empty-changeset` ensures
the script succeeds even when nothing needs updating.

---

## Parameters

All stack parameters have defaults. Override per-environment via `params/<env>.json`.

Key parameters to review in `params/prod.json`:

| Parameter | Current | Notes |
|-----------|---------|-------|
| `InstanceType` | `t4g.medium` | Graviton ARM (4 GiB, ~$14/mo reserved) |
| `AmiId` | Latest AL2023 ARM | `al2023-ami-kernel-default-arm64` (auto-resolved via SSM) |
| `SshCidr` | `0.0.0.0/0` | Restrict to your IP for production |
| `MinACU` / `MaxACU` | 0.5 / 2.0 | Aurora scaling range (cost vs headroom) |

---

## Existing infrastructure

The templates codify the current live setup. If deploying fresh,
they produce an equivalent environment. The following resources are
managed by CloudFormation:

| Stack | Resource | Live ID | Notes |
|-------|----------|---------|-------|
| — | VPC | `vpc-06e76bd6f283ed4a4` | Default VPC (not managed by CFN) |
| `quant-network` | EC2 SG | `sg-0c48c9010eaf84372` | Web + SSH |
| `quant-network` | RDS SG | `sg-0278c603461bbf8fa` | Postgres from EC2 only |
| `quant-database` | Aurora cluster | `quantdb-cluster` | Imported; Serverless v2, 0.5–2.0 ACU |
| `quant-compute` | EC2 | *(resolve via CFN `InstanceId` output)* | `quant-server`, t4g.medium ARM, 30 GiB root |
| `quant-compute` | IAM role | `quant-ec2-role` | SSM access |
| `quant-compute` | EIP | *(resolve via CFN `PublicIp` output)* | Static public IP |
| — | Key pair | `tradingServerKey` | SSH access (not managed by CFN) |
| — | S3 bucket | `quant-db-dumps-539163478329` | Prod `pg_dump` archive under `dumps/` (not managed by CFN). Private, AES256, 90-day expiry; `quant-ec2-role` may `PutObject` via bucket policy. See [Database dump & restore](../guides/database-dump-restore.md#prod-backup-to-s3) |

Instance and EIP IDs change when the compute stack replaces EC2 — resolve at
runtime from `quant-compute` outputs (`InstanceId`, `PublicIp`). See
[Dev vs Prod — resolve instance ID](dev-vs-prod.md#resolve-the-current-prod-ec2-instance-id).

---

## SSM parameters

All app secrets live under `/quant/<env>/` in SSM Parameter Store.

| Parameter | Type | Source |
|-----------|------|--------|
| `QUANTDB_HOST` | String | Aurora cluster endpoint |
| `QUANTDB_PORT` | String | `5432` |
| `QUANTDB_USERNAME` | SecureString | DB admin user |
| `QUANTDB_PASSWORD` | SecureString | DB admin password |
| `JWT_SECRET` | SecureString | `openssl rand -base64 32` |
| `EXCHANGE_SECRETS_KEY` | SecureString | Fernet key for `CORE_ADMIN.API_CREDENTIAL` — **required in prod** (`CredentialCrypto` fail-fast at API boot) |
| `ORIGIN_TLS_CERT` | SecureString | Cloudflare Origin Certificate (PEM) — written to `secrets/origin.pem` by the deploy job when `DOMAIN` is set |
| `ORIGIN_TLS_KEY` | SecureString | Cloudflare Origin private key (PEM) — written to `secrets/origin-key.pem`; enables the `docker-compose.cloudflare.yml` overlay |
| `CLOUDFLARE_API_TOKEN` | SecureString | Zone → DNS → Edit token for `aws/scripts/cloudflare-dns.sh` (DNS record management) |
| `CORS_ORIGINS` | String | `https://yourdomain.com` |
| `FUTU_HOST` | String | `127.0.0.1` |
| `FUTU_PORT` | String | `11111` |
| `TRADE_SERVICE_TOKEN` | SecureString | Shared secret for Lambda → API scheduled apply (auto-created by `init-ssm-params.sh`) |
| `CCXT_EGRESS_BYBIT` | String | *Optional.* Extra egress routes for keyed Bybit sessions, `uk=<ProxyUrl of quant-uk-egress>`. Each key is routed to whichever one Bybit accepts. See [UK egress proxy](#uk-egress-proxy) |

The app loads these at startup via `quant/shared/config.py` when `USE_SSM=1`.

**Note:** `JWT_SECRET` must be the same across all app instances sharing
a database — otherwise JWTs minted by one instance cannot be verified
by another. `EXCHANGE_SECRETS_KEY` must also be stable — rotating it
invalidates all stored credential ciphertext until users re-save keys.

---

## UK egress proxy

`quant-uk-egress` (eu-west-2) is a t4g.nano running squid behind Elastic IP
**`13.43.55.53`**. It accepts `CONNECT` on `:3128` only, only from the app host's
EIP (`ProxyClientCidr`, `52.221.3.230/32`), and only to `api.bybit.com`,
`api-testnet.bybit.com`, `api-demo.bybit.com` and `api.bytick.com`; any other
destination gets `403`. The application stays in Singapore; only **keyed**
Bybit traffic leaves from London. Live since 2026-09-23.

`ProxyClientCidr` is a literal in `aws/params/prod.json`, not a cross-stack
reference, because the stacks live in different regions. If `quant-compute`
replaces its Elastic IP, update that value and redeploy `uk-egress`, or every
keyed Bybit call times out at the proxy's security group.

### Request path

The proxy is a pipe, not a second site. squid opens a TCP tunnel and the TLS
session runs end to end between the `api` container and Bybit, so the London
host cannot read keys, orders or responses. It runs no application code, holds
no credentials, reads no SSM parameters, and has no route to Aurora.

```
api (Singapore) ──TLS inside CONNECT──► squid (London) ──► api.bybit.com
api (Singapore) ◄────── same tunnel ─── squid (London) ◄── response
     │
     └──► Aurora (Singapore): EXECUTION_EVENT, TRANSACTION, pause, schedule status
```

Every response, success or refusal, comes back to the Singapore process, which
interprets it and writes the result over its existing Aurora connection. So the
route needs no database configuration, and moving an order through London
changes nothing about where results are stored. The cost is latency: each keyed
call adds about one Singapore–London round trip (150–200 ms), which is
negligible for a few market orders per interval.

### Bootstrap

The instance's user data adds a 1 GiB swap file, installs squid, writes
`/etc/squid/squid.conf`, and enables the service. The swap is load-bearing.
0.5 GiB is enough for squid but not for `dnf`'s repository metadata: the first
boot ran `dnf -y update`, the kernel killed it for memory, and under `set -e`
squid was never installed. The instance and IP looked healthy, and every
connection to `:3128` was refused. The template no longer runs a full update.

User data runs once, at first boot. Editing it updates the stack with a
stop/start of the instance (about a minute without the `uk` route, same IP),
but it does not re-run on that instance. A change to the squid config has to be
applied by hand as well, or by replacing the instance.

### Checking it

From the app host (Session Manager on `quant-compute`'s `InstanceId`):

```bash
# 200 through the tunnel: squid is up and admits Bybit
curl -sS -o /dev/null -w '%{http_code}\n' -x http://13.43.55.53:3128 \
  https://api.bybit.com/v5/market/time
# 403 on CONNECT: the destination allowlist holds
curl -sS -o /dev/null -x http://13.43.55.53:3128 https://checkip.amazonaws.com
```

`Connection refused` on `:3128` means squid is not running (the packet reached
the host); a timeout means the security group or `ProxyClientCidr` is wrong. On
the proxy itself (Session Manager on `quant-uk-egress`'s `InstanceId`, region
`eu-west-2`): `systemctl status squid`, `/var/log/squid/access.log`, and
`/var/log/cloud-init-output.log` for boot failures.

In the app, a dead proxy surfaces as
`broker unreachable during load_markets: bybit GET …/instruments-info`, the
first request `load_markets` sends on the `uk` route. The router does not fall
back to `direct` from there (see *Connect* below).

### Per-key routing

The route is chosen **per API key**, not per venue, because each user pins
their own key at Bybit and can change that pin without telling us.

- **Candidates.** `EgressRoutes.from_env()` (`quant/trade/brokers/ccxt/egress.py`) returns `direct` (the
  Singapore EIP) followed by the named routes in `CCXT_EGRESS_<EXCHANGE_ID>`,
  e.g. `CCXT_EGRESS_BYBIT=uk=http://13.43.55.53:3128`. When the variable is unset,
  every key goes direct.
- **Connect.** `KeyRouter.connect(gateway)` (`quant/trade/brokers/ccxt/routing.py`)
  connects the session's own gateway on the cached route first, then the rest.
  `load_markets` is public and succeeds from anywhere, so the next call, Bybit
  `GET /v5/user/query-api` (`fetch_api_key_info`), is the first one the
  allowlist can refuse. `retCode 10010` (unmatched IP) disconnects and tries the
  next route. Any other failure stops with no fallback: if the proxy is down,
  the call fails as `BrokerConnectionError` rather than switching to an IP the
  key may reject. Only venues whose `classify_denial` recognises an IP refusal
  can be routed; others use their first route.
- **Cache.** The accepted route, the key's allowlist, `kycRegion`, `readOnly`,
  expiry, and any product the venue refused are stored as a `KeyProfile` in
  Redis at `key_profile:<exchange>:<demo|paper|live>:<sha256(api_key)[:16]>`,
  with a 1-day TTL. Nothing is written to the database. Every field can be
  re-read from the venue, and a key the user edits is caught on the next connect.
- **Refusals.** A read-only key (`KEY_READ_ONLY`), a product Bybit refused with
  `retCode 10024` (`REGION_RESTRICTED`), and "no route accepted"
  (`IP_NOT_ALLOWED`) all need an operator to fix them, so the scheduler pauses
  the deployment instead of retrying, whether the refusal came back as a
  rejected order or was raised while connecting. After one `10024`, later
  orders for that market type are refused before they are sent, until the
  cache entry expires.
- **Visibility.** The dry-run report carries `key_profile` (route, allowlist,
  KYC region, read-only, expiry, refused products), so the cutover can be
  checked from the UI rather than from the connect log line.
- Keyless sessions (`CcxtSessionConfig.public`, used for venue limits and market
  data) always go direct, since an IP allowlist binds a key and they carry none.
  Each keyed session logs `proxy=<url>` or `proxy=direct` on connect.

**Cutover** (done 2026-09-23; order matters, because a key rejects any IP it
does not list):

1. `aws ssm put-parameter --name /quant/prod/CCXT_EGRESS_BYBIT --type String --value uk=http://13.43.55.53:3128`
2. Restart `api` (SSM is read once at process start; `worker` never trades).
   Keys still pinned to Singapore keep going direct.
3. Check the proxy from the app host (see [Checking it](#checking-it)).
4. Add `13.43.55.53` to the Bybit key's IP allowlist and remove the old IP. The
   next session sees `10010` on direct and moves to `uk`, logging
   `Bybit key moved egress route direct → uk`.
5. Run a dry-run and confirm `key_profile.route` is `uk` in the report.

Skipping step 1 leaves the key refused with `(direct)` as the only route tried;
skipping step 3 hid a proxy that had never started.

**Rollback:** delete the parameter and restart `api`. Keys that only list the
London IP then fail as `IP_NOT_ALLOWED` and pause until the Singapore IP is
added back.

---

## Trade scheduler (EventBridge + Lambda)

Phase 1.9 AWS side — see [Scheduler & Price Bars](../design/scheduler-price-bars.md).

```
EventBridge Scheduler (one schedule per task, not per deployment)
        │  cron, event {"task": "trade_apply_tick",
        │               "path": "/api/v1/scheduler/tick"}   ← both from the YAML
        ▼
quant-scheduled-task Lambda ──POST──►  https://algodaemon.com/api/v1/scheduler/tick
        │                              Authorization: Bearer TRADE_SERVICE_TOKEN
        ▼                              (token fetched from SSM at Lambda cold start)
FastAPI on EC2 (every due deployment: bars → signal → order)
```

The Lambda is a **generic bridge**: the schedule's event carries both the task
name and the path to post to, so a new job is a YAML file in `config/scheduler/`
and nothing else — no handler change, no Lambda redeploy, no stack change.

Each row below is one file in `config/scheduler/`, which declares the `task`,
the `path`, the cron expression and whether it is enabled:

| Task | Schedule | Endpoint | Purpose |
|------|----------|----------|---------|
| `trade_apply_tick` | `cron(55 * * * ? *)` | `/api/v1/scheduler/tick` | Apply every due deployment, five minutes before bar close |
| `log_proc_summary` | `cron(15 23 * * ? *)` | `/api/v1/admin/log-proc-summary/summarize` | Aggregate `LOG_PROC_DETAIL` into daily summaries |
| `price_bar_sync` | `cron(0 * * * ? *)` | `/api/v1/market-data/price-bars/sync` | Warm `MARKET_DATA.PRICE_BAR` for scheduled deployments |
| `term_stale_connections` | `cron(45 * * * ? *)` | `/api/v1/admin/db/terminate-stale-connections` | Terminate `quant_app` idle Postgres sessions older than one hour |

No path takes substitution fields, and none points at
`/trade/deployments/{id}/apply`. That route requires a human — it trades on the
caller's own account — so a schedule aimed at it could only ever 401. The tick
resolves each deployment's owner from the database instead, which is what lets
one schedule serve every deployment.

Two things have to agree for a job to run: the `path` in the YAML and the route
FastAPI serves. A mismatch only shows up when the schedule fires, as a 404 on a
tick that is not retried, so `tests/unit/test_scheduled_task_paths.py` checks
every declared path against the routers behind the service-token gate, along
with the properties above.

!!! note "Why the path lives in the config, not the Lambda"
    It used to be a `_TASK_PATHS` map in `handler.py`, which made three files
    have to agree instead of two — and the map was a second copy of what the
    YAML already implied, kept in step only by that test. The handler now takes
    the path from the event and holds no task knowledge, so a job can be added
    or repointed without touching Lambda code.

    That map doubled as an allowlist of paths the service token could reach. The
    real control is the API's own gate: `require_user_or_service` admits the
    service token on exactly three routers, and anything acting on a user's
    account requires a human token and refuses the Lambda regardless of path.
    The handler still rejects a `path` that is a URL rather than an absolute
    path, so an event cannot redirect the token to another host.

!!! note "`price_bar_sync` at :00; `trade_apply_tick` at :05"
    The two jobs are staggered on purpose. Summarisation runs at `:15` on
    Saturdays to stay clear of deployments and container restarts. The bar warmer
    fires at `:00` and `BarWarmer` sleeps `DEFAULT_SETTLE_S` (10s) before reading
    the clock — that pause lets the exchange finish publishing the candle that
    just closed and keeps an early delivery from making `floor_to_period` land a
    period back on a bar already stored.

    Apply runs at `:05` so the warm usually finishes first. A pass that runs
    after applies have fetched their own bars has done nothing for warming, but
    overlap is safe — the bar insert treats a unique violation as a concurrent
    write. Hourly cadence serves the `1H` interval; `DAILY` instruments are
    swept on every warm pass too and cost one coverage read each, returning
    immediately once the bar is stored.

`trade_apply_tick` waits `ScheduleSweeper.DEFAULT_SETTLE_S` (10s) after the
`:05` delivery before asking what is due — a cursor sitting exactly on the
boundary would answer "not yet" to a delivery a few milliseconds early and then
wait a whole interval.

**Prod only.** Dev boxes run an in-process poller inside FastAPI that supplies
the same wakeups on a timer — no EventBridge, Lambda, or service token. Both
drivers run the identical pass (`ScheduleSweeper`). See
[Scheduler design §6.2](../design/scheduler-price-bars.md#62-schedule-management-one-platform-tick-not-a-schedule-per-deployment).

**Slack + mainnet promotion:** when to move alerts to prod ops and orders to Bybit mainnet —
[Live Trading Promotion](../guides/live-trading-promotion.md).

| Resource | Name | Purpose |
|----------|------|---------|
| Schedule group (tasks) | `quant-system-jobs` | Task schedules from `config/scheduler/` — written by `scripts/sync_schedules.py` |
| Schedule group (legacy) | `quant-trade-deployments` | Created by CFN; per-deployment schedules were dropped in favour of the platform tick |
| Lambda | `quant-scheduled-task` | Task-routed HTTP bridge (`aws/lambda/scheduled-task/handler.py`) |
| IAM role | `quant-scheduler-invoke` | Assumed by EventBridge Scheduler to invoke Lambda |
| IAM role | `quant-scheduled-task-lambda` | Lambda execution (CloudWatch Logs + SSM read of `TRADE_SERVICE_TOKEN`) |
| IAM policy | `quant-ec2-scheduler-manage` | Attached to `quant-ec2-role` — boto3 create/update/delete schedules |

!!! warning "Schedule retry policy"
    Every schedule sets `RetryPolicy.MaximumRetryAttempts = 0`, in
    `scripts/sync_schedules.py`. EventBridge Scheduler's default (185 retries
    over 24h) would repeatedly re-invoke a failing trade apply — order-level
    retries live in the API (`OrderRetryExecutor`), and the scheduler tick's own
    attempt budget decides when to try a deployment again, on the next wakeup
    rather than seconds later.

    `quant-ec2-scheduler-manage` is now only used by that script. Application
    code creates no schedules: deployment create, update and stop write to the
    database alone, so there is no second source of truth to keep in step.

### Deploying

The `deploy` workflow owns this stack, same as the other four. Its `cfn` job runs
`bash aws/deploy.sh eventbridge` — CFN, then the Lambda zip upload, then
`scripts/sync_schedules.py` — whenever a push to `main` touches
`aws/cfn/eventbridge/scheduled-task.yml`, `aws/lambda/scheduled-task/**`, `aws/deploy.sh`, or
`config/scheduler/**`. A manual **Run workflow** deploys it unconditionally,
which is how you redeploy without an infra commit.

Running it by hand needs `boto3` and `pyyaml` importable by the `python3` on
your PATH — `sync_schedules.py` is invoked as a plain script, so having them in
the repo's `env/` does not count. The deploy checks this before touching
CloudFormation and tells you what to install. The Lambda package itself is built
with the standard library (`python3 -m zipfile`), so no `zip` binary is needed
on the runner or the host.

One bootstrap step still needs admin credentials, because the GitHub deploy user
can read SSM but not write it:

```bash
# Once per environment — the deploy fails with instructions if it is missing.
aws ssm put-parameter --name /quant/prod/TRADE_SERVICE_TOKEN \
  --value "$(openssl rand -base64 32)" --type SecureString \
  --region ap-southeast-1
```

The API host picks the same value up automatically: it runs with `USE_SSM=1`,
and `load_config()` loads every parameter under `/quant/prod/` into the
environment, where `require_user_or_service` reads it.

Smoke-test the Lambda directly once the stack is up:

```bash
aws lambda invoke \
  --function-name quant-scheduled-task \
  --payload '{"task":"log_proc_summary"}' \
  --cli-binary-format raw-in-base64-out \
  /tmp/out.json && cat /tmp/out.json
```

### Scheduling from the UI

Deployments can be put on a schedule from **`DeploymentDialog`** (create) or
**`ScheduleCell`** (inline edit on the deployments table). Manual is the default;
the hourly platform tick (`trade_apply_tick`) picks up any non-null schedule.
Platform schedulers (`price_bar_sync`, `trade_apply_tick`) need no separate toggle.
See [scheduler design §3.1](../design/scheduler-price-bars.md#31-product-ux-how-scheduling-is-enabled).

Per-deployment EventBridge schedules were dropped in favour of the platform tick
([scheduler design §6.2](../design/scheduler-price-bars.md#62-schedule-management-one-platform-tick-not-a-schedule-per-deployment)).
The service token is accepted by the `admin`, `market_data`, and `scheduler` routers.

### Outputs to use from the app

```bash
aws cloudformation describe-stacks --stack-name quant-scheduler \
  --query 'Stacks[0].Outputs' --output table
```

| Output | Used by |
|--------|---------|
| `ScheduledTaskLambdaArn` | `sync_schedules.py` — schedule `Target.Arn` |
| `SchedulerInvokeRoleArn` | `sync_schedules.py` — schedule `Target.RoleArn` |
| `ScheduleGroupName` | `sync_schedules.py` — `GroupName` |

---

## Tearing down

```bash
# Reverse order — scheduler/compute first, network last
aws cloudformation delete-stack --stack-name quant-scheduler
aws cloudformation delete-stack --stack-name quant-compute
aws cloudformation delete-stack --stack-name quant-database   # DeletionPolicy: Retain
aws cloudformation delete-stack --stack-name quant-network
```

The database stack has `DeletionPolicy: Retain` — Aurora resources are
kept even if the stack is deleted (imported resources). `DeletionProtection: true`
prevents accidental deletion (disable it manually first if you really mean to).

---

## CI/CD — GitHub Actions

Push to `main` triggers an automated deploy pipeline (`.github/workflows/deploy.yml`):

```
push to main → changes (path filter) ─┬─→ test ──→ build-app (quant/** only)
               frontend (build+audit) ┼─→ build-nginx (frontend/** only)
               cfn (infra, parallel) ──┤
               migrate (db, gated) ────┘
                                       ▼
                                    deploy (SSM: selective pull + up + REFDATA refresh)
```

`deploy` waits on `test`, `cfn`, `build-app`, `build-nginx`, and `migrate` (most may be skipped). `build-app` depends on **Python tests only**; `build-nginx` still requires the frontend job — so a SPA build failure does not block shipping `quant-app`.

The workflow uses `paths-ignore` for `docs/**`, `*.md`, `tests/**`, `scripts/**`, `.github/skills/**`, `.github/instructions/**`, `.cursor/**` — pushes touching only ignored paths do **not** trigger the workflow. A push to `db/liquidbase/**` **does** trigger the workflow (so the `migrate` job can run). The docs site has its own workflow (`.github/workflows/docs.yml`).

### Docs workflow — the mermaid gate

`docs.yml` runs two jobs: `mermaid`, then `deploy` (which `needs` it). The gate
exists because **a malformed diagram does not fail `mkdocs build`**. MkDocs emits
the block as `<pre class="mermaid">` whatever it contains, `mermaid-init.js`
flattens it to raw text, and `mermaid.run()` only then throws — in the reader's
browser. The result is the diagram source displayed as a code block, with a green
build behind it. Two diagrams sat broken in the wiki that way.

`scripts/mermaid-check/check.mjs` parses every ```` ```mermaid ```` fence under
`docs/` with the real mermaid parser (via jsdom, since mermaid is a browser
library) and exits non-zero on the first failure, naming `file:line`. Run it
locally the same way CI does:

```bash
cd scripts/mermaid-check && npm ci
node scripts/mermaid-check/check.mjs docs   # from the repo root
```

Parsing the raw fence is faithful to what the browser parses: MkDocs escapes the
block to entities (`--&gt;`), but `mermaid-init.js` reads it back through
`code.textContent`, which unescapes them.

Two syntax traps account for both historical breakages — a `;` inside a
sequence-diagram message, which mermaid reads as a statement separator, and a
bare quoted string where a node id belongs (`-->|authed| "Redirect /"` rather
than `-->|authed| RedirectHome["Redirect /"]`).

### How it works

1. **Changes job** — `dorny/paths-filter` detects which artifacts changed:
   - **app** — `quant/**`, `Dockerfile`, `requirements.txt`, `config/db-targets.json`
   - **nginx** — `frontend/**`, `docker/nginx/**`
   - **compose** — `docker-compose.yml`, `docker-compose.prod.yml`, `docker-compose.tls.yml`, `docker-compose.cloudflare.yml`
   - **deploy** — true when any of app / nginx / compose changed (gate for the deploy job)
   - **db** — `db/liquidbase/**` (gate for the migrate job)
   - **refdata** — `db/liquidbase/refdata/**` (gate for post-migrate Redis republish)
2. **Test job** — runs `pytest tests/unit/` on GitHub's runner (Python 3.12)
3. **Frontend job** — `npm ci`, `npm audit --audit-level=high`, `npm run build` (type-check + Vite build), `npm test` on Node 24. Gates **`build-nginx` only** — not `build-app`.
4. **CFN job** — deploys infra stacks when the matching `aws/cfn/<service>/*.yml` template or relevant `aws/params/prod.json` keys change (per-stack detection). A template that git reports as a **pure rename** (`R100` — moved, not one byte changed) is dropped from the changed list before the per-stack checks, so moving templates between folders deploys nothing. The **database** stack only deploys when `cfn/database/aurora-cluster.yml` / DB params change and requires the `DB_MASTER_PASSWORD` secret (it is otherwise guarded by `DeletionPolicy=Retain`, `UpdateReplacePolicy=Snapshot`, `DeletionProtection=true`).
5. **Build jobs** — `build-app` when `quant/**` (etc.) changed; `build-nginx` when `frontend/**` changed. Each pushes to ECR (git SHA + `latest`) on native arm64 — see [Why the build runs on arm64](#why-the-build-runs-on-arm64).
6. **Migrate job** — skipped unless `db/liquidbase/**` changed; otherwise runs `aws/scripts/liquibase-ssm-run.sh deploy <sha>` on EC2 with `LIQUIBASE_CONTEXTS=prod-deploy`. Gated by the `production-db` environment (see [Approving a migration](#approving-a-migration)).
7. **Deploy job** — skipped when no app/nginx/compose/db changes; SSM Run Command runs the inline deploy script (see [Deployment logic](#deployment-logic) below). Waits on `migrate`, so containers never restart ahead of the schema. Sets `REFRESH_REFDATA` after a REFDATA migrate when `quant-app` was not rebuilt.

**Manual full deploy:** Actions → deploy → Run workflow (`workflow_dispatch`). Rebuilds both images and deploys regardless of paths. The optional `deploy_database` input (default off) additionally deploys the RDS stack — leave unchecked unless you intend an Aurora change.

Rollback: re-run the workflow on an older commit (images tagged by SHA), or redeploy with a previous `IMAGE_TAG=<older-git-sha>`.

No SSH keys needed — deploy uses SSM Run Command (same IAM role the EC2 already has).

!!! note "Frontend build vs CI check"
    The production SPA bundle ships **inside the quant-nginx Docker image** (built in CI for arm64). The separate `frontend` runner job is a fast **validation gate** (build + `npm audit` + unit tests) — it does not produce the deployed artifact.

### Why the build runs on arm64

The EC2 host is Graviton, so the images must be `linux/arm64`. That used to be produced by cross-building from an x64 runner under QEMU, which made image builds bimodal: ~1 min when `requirements.txt` was untouched and BuildKit reused the cached pip layer, but 4–17 min whenever it changed.

Emulation bought nothing. Every dependency resolves to a prebuilt `manylinux_2_28_aarch64` wheel, and the only source build (`futu-api`) finishes in seconds. What QEMU actually slowed down was pip unpacking ~120 wheels and byte-compiling them to `.pyc` — a single phase that took 288s of an 8m build on 2026-08-11.

Two changes address it:

- **`runs-on: ubuntu-24.04-arm`** and no `setup-qemu-action`. Native arm64 runners are free and unlimited on public repos, with the same 4 vCPU / 16 GB as the x64 ones.
- **`requirements.txt` is runtime-only.** `pytest`, `mkdocs-material` and `pyyaml` moved to `requirements-dev.txt`, which starts with `-r requirements.txt`. That drops ~18 packages of test and docs tooling (mkdocs, babel, pygments, watchdog, …) out of the API and worker containers — nothing under `quant/` imports them.

Install `requirements-dev.txt` locally; `setup.sh` and the CI test jobs already do. The `Dockerfile` installs `requirements.txt` alone, so a package added there ships to production.

### Deployment logic

The `deploy` job sends one `AWS-RunShellScript` SSM command to the EC2 and polls `ssm get-command-invocation` for up to ~15 min. The inline script (in `.github/workflows/deploy.yml`, `deploy` job) does, in order:

1. **Resolve target** — `InstanceId` from the `quant-compute` CFN output (falls back to the `EC2_INSTANCE_ID` repo var).
2. **Sync source** — clone `/opt/quant` if missing, else `git fetch --prune` + `git reset --hard origin/main` (compose/nginx config come from the repo).
3. **TLS overlay** — when the `DOMAIN` repo var is set, fetch `ORIGIN_TLS_CERT` / `ORIGIN_TLS_KEY` from SSM into `secrets/`; if both land, append `-f docker-compose.cloudflare.yml`. Missing cert/key → stay HTTP-only with a warning.
4. **Disk hygiene** — `docker builder prune -af` + `docker image prune -af` before pulling (the 8→30 GiB volume history made this necessary).
5. **Digest-aware pull** — per service, compare the ECR image digest to the local one; **skip the pull when they match**. Tag resolution falls back from `${git_sha}` to `latest` if the SHA tag is missing.
6. **Selective `up`** — only the changed services restart: `DEPLOY_APP` → `api`+`worker`, `DEPLOY_NGINX` → `nginx`, `DEPLOY_COMPOSE` → full `up -d --remove-orphans`. All `up` calls use `--no-build` so prod **never** builds on EC2. `DEPLOY_APP` is set when `quant/**` changed **or** the `build-app` job pushed an image in the same run. After a REFDATA-only migrate, `REFRESH_REFDATA` runs `quant.refdata.publisher` inside `quant-api` without a full app rebuild. See [Production Rollout](../guides/prod-rollout.md).
7. **Split image builds** — `build-app` depends on Python tests only; `build-nginx` still waits on the frontend job. A frontend build failure no longer blocks shipping `quant-app`.
8. **Report** — `docker image prune -f`, then `docker compose ps`; the job tails the SSM `StandardOutputContent` and fails on `Failed`/`TimedOut`/`Cancelled`.

!!! note "A compose-only deploy still restarts `api` and `nginx`"
    `DEPLOY_COMPOSE` runs `up -d --remove-orphans`, which recreates a service
    when its **effective config** changes — and that includes the image
    *reference string*, not just the image contents. On a push that touches only
    a compose file, `build-app` and `build-nginx` are skipped, so
    `resolve_app_tag` finds no image for the new commit SHA and falls back to
    `latest`. `APP_IMAGE` therefore flips from
    `quant-app:<previous-sha>` to `quant-app:latest`, compose sees a changed
    service, and `api` + `worker` + `nginx` all restart even if only the
    `worker` block was edited (observed on `423f9884d`, which edited `worker`
    alone). `redis` is unaffected — its image is pinned to `redis:7-alpine`.

    The bits are identical: `latest` and the previous SHA tag resolve to the
    same digest, so this is a seconds-long restart, not a version change.
    Two consequences worth knowing: expect a brief API blip on any compose-only
    deploy, and the running containers are afterwards tracked by `latest`
    rather than a pinned SHA, so read the digest rather than the tag when
    establishing what is deployed.

### GitHub setup (one-time)

**Secrets** (repo → Settings → Secrets and variables → Actions → Secrets):

| Secret | Value | How to get it |
|--------|-------|---------------|
| `AWS_ACCESS_KEY_ID` | IAM user access key | Deploy IAM user (`quant_deploy`) with SSM Run Command, CFN deploy, and ECR push policies attached |
| `AWS_SECRET_ACCESS_KEY` | IAM user secret key | Same IAM user |
| `DB_MASTER_PASSWORD` | Aurora master password | **Only** needed to deploy the `quant-database` stack (manual `workflow_dispatch` with `deploy_database` checked). Without it the `cfn` job fails fast instead of hanging on an interactive prompt. |

**Variables** (repo → Settings → Secrets and variables → Actions → Variables):

| Variable | Value |
|----------|-------|
| `EC2_INSTANCE_ID` | *(optional fallback only)* | Deploy workflow resolves `InstanceId` from the `quant-compute` stack at runtime; set this var only if CFN lookup fails |
| `DOMAIN` | Public domain (e.g. `algodaemon.com`). When set, the deploy job fetches `ORIGIN_TLS_CERT`/`ORIGIN_TLS_KEY` from SSM and merges `docker-compose.cloudflare.yml` for HTTPS. Unset → HTTP-only. |

**Environments** (repo → Settings → Environments):

- `production` — used by `build-app`, `build-nginx`, `cfn`, and `deploy`. No protection rules; it exists to scope secrets, not to gate.
- `production-db` — used by `migrate` only. Carries a **required reviewer**, which is what makes a schema change wait for a human.

### Approving a migration

A push touching `db/liquidbase/**` parks the `migrate` job in *Waiting* and notifies the reviewer. Approve it in the run page and the migration proceeds, then `deploy` restarts the containers. Reject it and `deploy` is held back too, so prod keeps both the old schema and the old image — a consistent pair.

Only `migrate` is gated. An app-only push still deploys with no prompt; gating every job would mean approving container-only changes as well, and a reviewer who clicks through by reflex is not a gate.

The job runs against `github.sha`, not `main`. Approval can sit for hours, and pinning the commit means the migration that runs is the one that was reviewed, even if `main` has moved on.

Two things the gate deliberately does not do. It shows a job name rather than a diff, so it catches an unintended migration but cannot tell you whether the SQL is correct — read the changesets before approving. And it does not distinguish a one-line procedure edit from a schema rewrite: nearly every procedure and function file under `db/liquidbase/` sits behind an active `prod-deploy` `runOnChange` changeset, so editing any of them queues this job.

### Bootstrap the EC2 (one-time)

Before the first deploy, run on the EC2:

```bash
# SSH or SSM session into the instance, then:
bash /opt/quant/aws/scripts/bootstrap-ec2.sh
```

Or remotely via SSM (resolve instance ID from CFN — it changes on EC2 replacement):

```bash
INSTANCE_ID="$(aws cloudformation describe-stacks --stack-name quant-compute \
  --region ap-southeast-1 \
  --query "Stacks[0].Outputs[?OutputKey=='InstanceId'].OutputValue" --output text)"

aws ssm send-command \
  --instance-ids "$INSTANCE_ID" \
  --document-name AWS-RunShellScript \
  --parameters file://aws/scripts/ssm-ec2-deploy.json \
  --region ap-southeast-1
```

Or for disk recovery:

```bash
aws ssm send-command \
  --instance-ids "$INSTANCE_ID" \
  --document-name AWS-RunShellScript \
  --parameters file://aws/scripts/ssm-ec2-recover.json \
  --region ap-southeast-1
```

!!! warning "SSM `--parameters` escaping"
    Do **not** pass long inline `commands=[...]` strings from a local shell — bash will expand `$VAR` and break JSON (`ParamValidation` / empty `CommandId`). Use `--parameters file://aws/scripts/ssm-ec2-deploy.json` (or `ssm-ec2-deploy-inline.json` before `ec2-deploy.sh` is on `main`). SSM runs without `$HOME`; scripts set `export HOME=/root` and `git config --global --add safe.directory /opt/quant`.

One-time bootstrap (legacy curl):

```bash
INSTANCE_ID="$(aws cloudformation describe-stacks --stack-name quant-compute \
  --region ap-southeast-1 --profile alfcheun \
  --query "Stacks[0].Outputs[?OutputKey=='InstanceId'].OutputValue" --output text)"

aws ssm send-command \
  --instance-ids "$INSTANCE_ID" \
  --document-name AWS-RunShellScript \
  --parameters 'commands=["curl -fsSL https://raw.githubusercontent.com/alfred1123/Quant_Strategies/main/aws/scripts/bootstrap-ec2.sh | sudo -u ec2-user bash"]' \
  --profile alfcheun --region ap-southeast-1
```

### Manual deploy

```bash
# Trigger from GitHub (no code push needed)
gh workflow run deploy
```

### Troubleshooting — disk full on deploy

Default AL2023 root volume is **8 GiB** — too small once Docker accumulates old build layers from pre-ECR deploys.

**Symptoms:** `no space left on device` during pull/extract; Compose warns `Some service image(s) must be built from source` and tries to **build on EC2** (never do this in prod).

**Immediate recovery (SSM on EC2):**

```bash
INSTANCE_ID="$(aws cloudformation describe-stacks --stack-name quant-compute \
  --region ap-southeast-1 \
  --query "Stacks[0].Outputs[?OutputKey=='InstanceId'].OutputValue" --output text)"

aws ssm send-command \
  --instance-ids "$INSTANCE_ID" \
  --document-name AWS-RunShellScript \
  --parameters file://aws/scripts/ssm-ec2-recover.json \
  --region ap-southeast-1
# Then re-run the GitHub deploy workflow, or:
aws ssm send-command \
  --instance-ids "$INSTANCE_ID" \
  --document-name AWS-RunShellScript \
  --parameters file://aws/scripts/ssm-ec2-deploy.json \
  --region ap-southeast-1
```

**Long-term:** CFN `cfn/ec2/app-host.yml` sets **30 GiB gp3** root volume (`RootVolumeSize`). Update the live volume without replacing the instance:

```bash
# Find volume id for the instance root device, then:
aws ec2 modify-volume --volume-id vol-XXXXXXXX --size 30 --region ap-southeast-1
# On the instance after volume shows "optimizing" → "completed":
sudo growpart /dev/nvme0n1 1 && sudo xfs_growfs /
```

Deploy script uses `--no-build` on all `compose up` commands so prod never builds on EC2.

---

## Future: ECS migration

The 2026-09-22 [capacity review](../design/infra-capacity-review.md) found the
single `t4g.medium` at 1.7 % average CPU with one core idle even under a
31-job batch, and concluded that neither a larger instance nor a second host is
warranted (decision #75). That page lists the metric triggers that would reopen
the question. Until one fires, the work is memory limits on the `worker`
service, CloudWatch alarms, and closing port 22 — not topology.

When the workload outgrows a single EC2 (e.g. independent queue worker
scaling), add an ECS stack:

1. Reuse existing ECR repos (`cfn/ecr/image-repositories.yml` — `quant-app`, `quant-nginx`)
2. Create `05-ecs.yml` for ECS cluster, ALB, API service, worker service
3. The same Docker images and SSM parameters work unchanged
4. Remove the compute stack (`cfn/ec2/app-host.yml`) when ready
