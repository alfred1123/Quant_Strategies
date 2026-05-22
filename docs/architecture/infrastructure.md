# Infrastructure

Infrastructure as Code for the Quant Strategies deployment.
All resources are defined as CloudFormation templates under `aws/cfn/`
and deployed via the AWS CLI.

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

SSM Parameter Store supplies secrets (`JWT_SECRET`, DB credentials) at app startup.

The base `docker-compose.yml` exposes nginx on **:80** (HTTP, using `nginx.dev.conf`). Adding `docker-compose.tls.yml` on top swaps in `nginx.conf` and adds **:443** (HTTPS with Let's Encrypt).

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
│   └── 03-compute.yml         ← EC2 + IAM role + EIP
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

---

## Deploying

### First time — bootstrap secrets

```bash
# Set up SSM parameters (prompts for DB password and JWT secret)
bash aws/scripts/init-ssm-params.sh
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
| `quant-compute` | EC2 | `i-03a670ddc9169233a` | `quant-server`, t4g.medium ARM |
| `quant-compute` | IAM role | `quant-ec2-role` | SSM access |
| `quant-compute` | EIP | `52.221.3.230` | Static public IP |
| — | Key pair | `tradingServerKey` | SSH access (not managed by CFN) |

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
| `CORS_ORIGINS` | String | `https://yourdomain.com` |
| `FUTU_HOST` | String | `127.0.0.1` |
| `FUTU_PORT` | String | `11111` |

The app loads these at startup via `quant/shared/config.py` when `USE_SSM=1`.

**Note:** `JWT_SECRET` must be the same across all app instances sharing
a database — otherwise JWTs minted by one instance cannot be verified
by another.

---

## Tearing down

```bash
# Reverse order — compute first, network last
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
push to main → changes (path filter) → test + cfn (parallel)
            → build-and-push (only changed images) → deploy (SSM: selective pull + up)
```

The workflow uses `paths-ignore` for `docs/**`, `tests/**`, `db/**`, `scripts/**`, `*.md`, etc. — pushes touching only ignored paths do **not** trigger the workflow. The docs site has its own workflow (`.github/workflows/docs.yml`).

### How it works

1. **Changes job** — `dorny/paths-filter` detects which artifacts changed:
   - **app** — `quant/**`, `Dockerfile`, `requirements.txt`
   - **nginx** — `frontend/**`, `docker/nginx/**`
   - **compose** — `docker-compose*.yml`
2. **Test job** — runs `pytest tests/unit/` on GitHub's runner
3. **CFN job** — deploys infra stacks when `aws/cfn/**` or relevant `aws/params/**` keys change
4. **Build-and-push job** — skipped when neither app nor nginx changed; otherwise builds only the affected image(s) and pushes to ECR (tags: git SHA + `latest`)
5. **Deploy job** — skipped when no app/nginx/compose changes; otherwise SSM Run Command: `git pull`, selective `docker compose pull` + `up -d` per changed service. Skips ECR pull when local image digest already matches. **Liquibase is not run automatically** — apply DB migrations manually when ready (see [Database](database.md#deployment)).

**Manual full deploy:** Actions → deploy → Run workflow (rebuilds both images and deploys regardless of paths).

Rollback: re-run the workflow on an older commit (images tagged by SHA).

No SSH keys needed — deploy uses SSM Run Command (same IAM role the EC2 already has).

!!! note "Frontend build"
    The SPA is built inside the **quant-nginx** Docker image in CI (arm64). No separate npm job on the runner.

### GitHub setup (one-time)

**Secrets** (repo → Settings → Secrets and variables → Actions → Secrets):

| Secret | Value | How to get it |
|--------|-------|---------------|
| `AWS_ACCESS_KEY_ID` | IAM user access key | Create a deploy IAM user with `ssm:SendCommand` + `ssm:GetCommandInvocation` |
| `AWS_SECRET_ACCESS_KEY` | IAM user secret key | Same IAM user |

**Variables** (repo → Settings → Secrets and variables → Actions → Variables):

| Variable | Value |
|----------|-------|
| `EC2_INSTANCE_ID` | *(optional fallback)* | Prefer CFN `quant-compute` → `InstanceId` output (current: `i-03a670ddc9169233a`) |

**Environment**: Create a `production` environment (repo → Settings → Environments) for deploy approvals (optional).

### Bootstrap the EC2 (one-time)

Before the first deploy, run on the EC2:

```bash
# SSH or SSM session into the instance, then:
bash /opt/quant/aws/scripts/bootstrap-ec2.sh
```

Or remotely via SSM:

```bash
aws ssm send-command \
  --instance-ids i-03a670ddc9169233a \
  --document-name AWS-RunShellScript \
  --parameters 'commands=["curl -fsSL https://raw.githubusercontent.com/alfred1123/Quant_Strategies/main/aws/scripts/bootstrap-ec2.sh | sudo -u ec2-user bash"]' \
  --profile alfcheun --region ap-southeast-1
```

### Manual deploy

```bash
# Trigger from GitHub (no code push needed)
gh workflow run deploy
```

---

## Future: ECS migration

When the workload outgrows a single EC2 (e.g. independent queue worker
scaling), add an ECS stack:

1. Reuse existing ECR repos (`00-ecr.yml` — `quant-app`, `quant-nginx`)
2. Create `05-ecs.yml` for ECS cluster, ALB, API service, worker service
3. The same Docker images and SSM parameters work unchanged
4. Remove the compute stack (`03-compute.yml`) when ready
