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
                               │  HTTPS :443
                               ▼
                   ┌───────────────────────┐
                   │   EC2  (t4g.small)    │
                   │                       │
                   │  ┌─────────────────┐  │
                   │  │  nginx          │  │  TLS termination (Let's Encrypt)
                   │  │  :443 → :8000   │  │  Static files (frontend/dist/)
                   │  └────────┬────────┘  │
                   │           │           │
                   │  ┌────────▼────────┐  │
                   │  │  uvicorn        │  │  FastAPI on 127.0.0.1:8000
                   │  │  (Docker)       │  │
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

---

## Directory layout

```
aws/
├── import-db-resources.json   ← resource mapping used during Aurora import
├── deploy.sh                  ← deploy / update all stacks
├── cfn/
│   ├── 01-network.yml         ← security groups (EC2 + RDS)
│   ├── 02-database.yml        ← Aurora PostgreSQL Serverless v2
│   └── 03-compute.yml         ← EC2 + IAM role + EIP
├── params/
│   └── prod.json              ← parameter values for prod
└── scripts/
    └── init-ssm-params.sh     ← bootstrap SSM secrets (run once)
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
| `InstanceType` | `t4g.small` | Graviton ARM (2 GiB, ~$7/mo reserved) |
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
| `quant-compute` | EC2 | `i-096f85bf84852cce3` | `quant-server`, t4g.small ARM |
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

The app loads these at startup via `api/config.py` when `USE_SSM=1`.

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
push to main → run tests → SSM Run Command → EC2 pulls + rebuilds containers
```

### How it works

1. **Test job** — runs `pytest tests/unit/` on GitHub's runner
2. **Deploy job** — uses AWS credentials to send an SSM `RunShellScript` command to the EC2
3. **On the EC2** — `git pull`, `docker compose up -d --build`, prune old images

No SSH keys needed — deploy uses SSM Run Command (same IAM role the EC2 already has).

### GitHub setup (one-time)

**Secrets** (repo → Settings → Secrets and variables → Actions → Secrets):

| Secret | Value | How to get it |
|--------|-------|---------------|
| `AWS_ACCESS_KEY_ID` | IAM user access key | Create a deploy IAM user with `ssm:SendCommand` + `ssm:GetCommandInvocation` |
| `AWS_SECRET_ACCESS_KEY` | IAM user secret key | Same IAM user |

**Variables** (repo → Settings → Secrets and variables → Actions → Variables):

| Variable | Value |
|----------|-------|
| `EC2_INSTANCE_ID` | `i-096f85bf84852cce3` |

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
  --instance-ids i-096f85bf84852cce3 \
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

1. Create `04-ecr.yml` for container image repositories
2. Create `05-ecs.yml` for ECS cluster, ALB, API service, worker service
3. The same Docker images and SSM parameters work unchanged
4. Remove the compute stack (`03-compute.yml`)
