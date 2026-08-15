# Infrastructure

Infrastructure as Code for the Quant Strategies deployment.
All resources are defined as CloudFormation templates under `aws/cfn/`
and deployed via the AWS CLI.

See [System Overview](overview.md) for runtime topology and [Dev vs Prod](dev-vs-prod.md) for environment differences.

---

## Architecture

```
                        ┌──────────────┐
                        │   Internet   │
                        └──────┬───────┘
                               │  HTTP :80  (HTTPS :443 with TLS overlay)
                               ▼
                   ┌───────────────────────┐
                   │   EC2  (t4g.medium)   │
                   │                       │
                   │  ┌─────────────────┐  │
                   │  │  nginx          │  │  SPA (ECR quant-nginx)
                   │  │  :80 → api:8000 │  │
                   │  └────────┬────────┘  │
                   │           │           │
                   │  ┌────────▼────────┐  │
                   │  │  api + worker   │  │  FastAPI + queue worker (ECR quant-app)
                   │  │  redis          │  │
                   │  └────────┬────────┘  │
                   │           │           │
                   └───────────┼───────────┘
                               │  VPC direct :5432
                               ▼
                   ┌───────────────────────┐
                   │  Aurora Serverless v2  │
                   │  PostgreSQL 17.9       │
                   │  0.5 – 2.0 ACU        │
                   └───────────────────────┘
```

SSM Parameter Store supplies secrets (`JWT_SECRET`, `EXCHANGE_SECRETS_KEY`, DB credentials) at app startup.

The base `docker-compose.yml` exposes nginx on **:80** (HTTP, using `nginx.dev.conf`). For HTTPS there are two overlays:

- **`docker-compose.cloudflare.yml`** — production default. Site sits behind Cloudflare (orange cloud) with a **Cloudflare Origin Certificate** terminating TLS at nginx (`nginx.cloudflare.conf`, `:443`). Wired automatically by the deploy pipeline when the `DOMAIN` GitHub variable and `/quant/prod/ORIGIN_TLS_CERT` + `ORIGIN_TLS_KEY` SSM params are present. See [HTTPS via Cloudflare](../guides/https-cloudflare.md).
- **`docker-compose.tls.yml`** — alternative for a DNS-only (grey cloud) / no-CDN setup. Swaps in `nginx.conf` and adds **:443** with Let's Encrypt (certbot).

---

## Directory layout

```
aws/
├── import-db-resources.json   ← resource mapping used during Aurora import
├── deploy.sh                  ← deploy / update all stacks
├── cfn/
│   ├── 00-ecr.yml             ← ECR repos quant-app, quant-nginx
│   ├── 01-network.yml         ← security groups (EC2 + RDS)
│   ├── 02-database.yml        ← Aurora PostgreSQL Serverless v2
│   ├── 03-compute.yml         ← EC2 + IAM role + EIP
│   └── 04-scheduler.yml       ← EventBridge Scheduler + scheduled-task Lambda
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

Stacks must be deployed in order due to cross-stack references.

| # | Stack | Template | Creates |
|---|-------|----------|---------|
| 0 | `quant-ecr` | `00-ecr.yml` | ECR repos `quant-app`, `quant-nginx` |
| 1 | `quant-network` | `01-network.yml` | EC2 SG (22/80/443), RDS SG (5432 from EC2 only) |
| 2 | `quant-database` | `02-database.yml` | Aurora cluster, serverless instance, DB subnet group |
| 3 | `quant-compute` | `03-compute.yml` | EC2 instance, IAM role (SSM access), Elastic IP |
| 4 | `quant-scheduler` | `04-scheduler.yml` | scheduled-task Lambda, EventBridge schedule group, invoke + EC2 manage IAM |

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
bash aws/deploy.sh network
bash aws/deploy.sh database
bash aws/deploy.sh compute
bash aws/deploy.sh scheduler   # normally CI; requires /quant/prod/TRADE_SERVICE_TOKEN in SSM
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

The app loads these at startup via `quant/shared/config.py` when `USE_SSM=1`.

**Note:** `JWT_SECRET` must be the same across all app instances sharing
a database — otherwise JWTs minted by one instance cannot be verified
by another. `EXCHANGE_SECRETS_KEY` must also be stable — rotating it
invalidates all stored credential ciphertext until users re-save keys.

---

## Trade scheduler (EventBridge + Lambda)

Phase 1.9 AWS side — see [Scheduler & Price Bars](../design/scheduler-price-bars.md).

```
EventBridge Scheduler (per deployment)
        │  cron / rate, event {"task": "trade_apply", "deployment_id": "…"}
        ▼
quant-scheduled-task Lambda ──POST──►  https://algodaemon.com/api/v1/trade/deployments/{id}/apply
        │                              Authorization: Bearer TRADE_SERVICE_TOKEN
        ▼                              (token fetched from SSM at Lambda cold start)
FastAPI on EC2 (business logic: bars → signal → order)
```

The Lambda is a **generic task bridge** routed by `event.task` — the planned
price-bar ingestion schedule (Phase 1.9) reuses the same function with a
`price_bar_sync` task instead of a second Lambda.

**Prod only.** Dev boxes run `SCHEDULER_BACKEND=local` (the default when implemented): an
in-process poller inside FastAPI reads missed-due deployments via `SP_GET_MISSED_DUE_DEPLOYMENTS`
and applies them directly — no EventBridge, Lambda, or service token. See
[Scheduler design §6.2](../design/scheduler-price-bars.md#62-schedule-management-app--not-yet-wired).

**Slack + mainnet promotion:** when to move alerts to prod ops and orders to Bybit mainnet —
[Live Trading Promotion](../guides/live-trading-promotion.md).

| Resource | Name | Purpose |
|----------|------|---------|
| Schedule group | `quant-trade-deployments` | Holds one schedule per active deployment |
| Lambda | `quant-scheduled-task` | Task-routed HTTP bridge (`aws/lambda/scheduled-task/handler.py`) |
| IAM role | `quant-scheduler-invoke` | Assumed by EventBridge Scheduler to invoke Lambda |
| IAM role | `quant-scheduled-task-lambda` | Lambda execution (CloudWatch Logs + SSM read of `TRADE_SERVICE_TOKEN`) |
| IAM policy | `quant-ec2-scheduler-manage` | Attached to `quant-ec2-role` — API/boto3 create/update/delete schedules |

!!! warning "Schedule retry policy"
    When the app creates schedules via boto3, it **must** set
    `RetryPolicy.MaximumRetryAttempts = 0`. EventBridge Scheduler's default
    (185 retries over 24h) would repeatedly re-invoke a failing trade apply —
    order-level retries already live in the API (`OrderRetryExecutor`).

### Deploying

The `deploy` workflow owns this stack, same as the other four. Its `cfn` job runs
`bash aws/deploy.sh scheduler` — CFN, then the Lambda zip upload, then
`scripts/sync_schedules.py` — whenever a push to `main` touches
`aws/cfn/04-scheduler.yml`, `aws/lambda/scheduled-task/**`, `aws/deploy.sh`, or
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

### What this stack does **not** do yet

- Create per-deployment schedules (API/boto3 on deployment create — app work)
- Accept `TRADE_SERVICE_TOKEN` on the FastAPI `/apply` route — only the `admin`
  router takes the service token so far, so a `trade_apply` invoke returns **401**

### Outputs to use from the app

```bash
aws cloudformation describe-stacks --stack-name quant-scheduler \
  --query 'Stacks[0].Outputs' --output table
```

| Output | App use |
|--------|---------|
| `ScheduledTaskLambdaArn` | EventBridge schedule `Target.Arn` |
| `SchedulerInvokeRoleArn` | EventBridge schedule `Target.RoleArn` |
| `ScheduleGroupName` | `GroupName` when creating schedules |

---

## Tearing down

```bash
# Reverse order — scheduler/compute first, network last
aws cloudformation delete-stack --stack-name quant-scheduler
aws cloudformation delete-stack --stack-name quant-compute
aws cloudformation delete-stack --stack-name quant-database   # DeletionPolicy: Snapshot
aws cloudformation delete-stack --stack-name quant-network
```

The database stack has `DeletionPolicy: Retain` — Aurora resources are
kept even if the stack is deleted (imported resources). `DeletionProtection: true`
prevents accidental deletion (disable it manually first if you really mean to).

---

## CI/CD — GitHub Actions

Push to `main` triggers an automated deploy pipeline (`.github/workflows/deploy.yml`):

```
push to main → changes (path filter) ─┐
               test ──────────────────┤
               frontend (build+audit) ─┤
                                       ├─→ build-and-push (only changed images)
               cfn (infra, parallel) ──┘             │
                                                      ▼
                                                   deploy (SSM: selective pull + up)
```

`deploy` waits on `test`, `cfn`, and `build-and-push` (the last two may be skipped). `build-and-push` requires both `test` **and** `frontend` to pass.

The workflow uses `paths-ignore` for `docs/**`, `*.md`, `tests/**`, `db/**`, `scripts/**`, `.github/skills/**`, `.github/instructions/**`, `.cursor/**` — pushes touching only ignored paths do **not** trigger the workflow. The docs site has its own workflow (`.github/workflows/docs.yml`).

### How it works

1. **Changes job** — `dorny/paths-filter` detects which artifacts changed:
   - **app** — `quant/**`, `Dockerfile`, `requirements.txt`
   - **nginx** — `frontend/**`, `docker/nginx/**`
   - **compose** — `docker-compose.yml`, `docker-compose.prod.yml`, `docker-compose.tls.yml`, `docker-compose.cloudflare.yml`
   - **deploy** — true when any of app / nginx / compose changed (gate for the deploy job)
2. **Test job** — runs `pytest tests/unit/` on GitHub's runner (Python 3.12)
3. **Frontend job** — `npm ci`, `npm audit --audit-level=high`, `npm run build` (type-check + Vite build), `npm test` on Node 22. Validates the SPA on the runner; a build/audit/test failure blocks `build-and-push`.
4. **CFN job** — deploys infra stacks when the matching `aws/cfn/**` template or relevant `aws/params/prod.json` keys change (per-stack detection). The **database** stack only deploys when `02-database.yml` / DB params change and requires the `DB_MASTER_PASSWORD` secret (it is otherwise guarded by `DeletionPolicy=Retain`, `UpdateReplacePolicy=Snapshot`, `DeletionProtection=true`).
5. **Build-and-push job** — skipped when neither app nor nginx changed; otherwise builds only the affected image(s) for `linux/arm64` with GitHub Actions layer cache and pushes to ECR (tags: git SHA + `latest`). Runs on a native arm64 runner (`ubuntu-24.04-arm`), so there is no QEMU in the path — see [Why the build runs on arm64](#why-the-build-runs-on-arm64).
6. **Deploy job** — skipped when no app/nginx/compose changes; otherwise SSM Run Command runs the inline deploy script (see [Deployment logic](#deployment-logic) below). **Liquibase is not run automatically** — apply DB migrations manually when ready (see [Database](database.md#deployment)).

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

The `deploy` job sends one `AWS-RunShellScript` SSM command to the EC2 and polls `ssm get-command-invocation` for up to ~10 min. The inline script (in `.github/workflows/deploy.yml`, `deploy` job) does, in order:

1. **Resolve target** — `InstanceId` from the `quant-compute` CFN output (falls back to the `EC2_INSTANCE_ID` repo var).
2. **Sync source** — clone `/opt/quant` if missing, else `git fetch --prune` + `git reset --hard origin/main` (compose/nginx config come from the repo).
3. **TLS overlay** — when the `DOMAIN` repo var is set, fetch `ORIGIN_TLS_CERT` / `ORIGIN_TLS_KEY` from SSM into `secrets/`; if both land, append `-f docker-compose.cloudflare.yml`. Missing cert/key → stay HTTP-only with a warning.
4. **Disk hygiene** — `docker builder prune -af` + `docker image prune -af` before pulling (the 8→30 GiB volume history made this necessary).
5. **Digest-aware pull** — per service, compare the ECR image digest to the local one; **skip the pull when they match**. Tag resolution falls back from `${git_sha}` to `latest` if the SHA tag is missing.
6. **Selective `up`** — only the changed services restart: `DEPLOY_APP` → `api`+`worker`, `DEPLOY_NGINX` → `nginx`, `DEPLOY_COMPOSE` → full `up -d --remove-orphans`. All `up` calls use `--no-build` so prod **never** builds on EC2.
7. **Report** — `docker image prune -f`, then `docker compose ps`; the job tails the SSM `StandardOutputContent` and fails on `Failed`/`TimedOut`/`Cancelled`.

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

**Environment**: Create a `production` environment (repo → Settings → Environments) for deploy approvals (optional).

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

**Long-term:** CFN `03-compute.yml` sets **30 GiB gp3** root volume (`RootVolumeSize`). Update the live volume without replacing the instance:

```bash
# Find volume id for the instance root device, then:
aws ec2 modify-volume --volume-id vol-XXXXXXXX --size 30 --region ap-southeast-1
# On the instance after volume shows "optimizing" → "completed":
sudo growpart /dev/nvme0n1 1 && sudo xfs_growfs /
```

Deploy script uses `--no-build` on all `compose up` commands so prod never builds on EC2.

---

## Future: ECS migration

When the workload outgrows a single EC2 (e.g. independent queue worker
scaling), add an ECS stack:

1. Reuse existing ECR repos (`00-ecr.yml` — `quant-app`, `quant-nginx`)
2. Create `05-ecs.yml` for ECS cluster, ALB, API service, worker service
3. The same Docker images and SSM parameters work unchanged
4. Remove the compute stack (`03-compute.yml`) when ready
