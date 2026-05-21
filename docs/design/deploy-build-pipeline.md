# Deploy build pipeline — issue & fix plan

## TL;DR

We currently build container images **on the production EC2 host** (arm64
Graviton) inside the GitHub Actions → SSM deploy step. That couples our deploy
to a long-standing npm bug around cross-platform optional native dependencies
and forces fragile workarounds. The proper fix is to **build images in CI and
pull them on EC2** (ECR-based pipeline).

## The main issue

### Symptom

`docker compose build` on EC2 fails inside the nginx multistage build at the
frontend stage:

```
[nginx frontend-build 4/6] RUN npm ci
npm error code EBADPLATFORM
npm error notsup Unsupported platform for @rolldown/binding-linux-x64-gnu@1.0.x:
  wanted {"os":"linux","cpu":"x64"} (current: {"os":"linux","cpu":"arm64"})
```

### Root cause

`frontend/package.json` listed `@rolldown/binding-linux-x64-gnu` as a
**top-level `dependencies` entry**, which makes it required on every
platform. On arm64 npm correctly refuses it with EBADPLATFORM.

Vite already pulls in `rolldown`, which declares all platform bindings
(`linux-{x64,arm64}-{gnu,musl}`, `darwin-*`, `win32-*`, …) as
`optionalDependencies` — npm resolves the correct one at install time.
The manual pin shadowed that mechanism.

Fix: delete the line from `package.json`, regenerate `package-lock.json`.
The lockfile's binding entries are then correctly flagged
`"optional": true` and `npm ci` works cleanly on any arch.

### Why we're in this position

We build images **on the deploy host** because it was the simplest path when
the project started. That means every prod deploy must:

- pull source via `git`,
- run `docker compose build` (which runs `npm ci` for the frontend),
- on the **target architecture** of the EC2 box (arm64).

This makes the build sensitive to the host's CPU/libc, and any package that
ships native bindings (rolldown, esbuild, swc, sharp, lightningcss…) becomes
a potential blocker. It also means CI never actually validates the production
image — only that local tests pass.

## Current tactical mitigation (deployed)

Removed the stray `@rolldown/binding-linux-x64-gnu` entry from
[`frontend/package.json`](../../frontend/package.json) and regenerated
[`frontend/package-lock.json`](../../frontend/package-lock.json).
[`docker/nginx/Dockerfile`](../../docker/nginx/Dockerfile) uses normal
`npm ci`.

This unblocks deploys but doesn't address the underlying anti-pattern of
building images on the prod host. The class of failure (a future
optional native dep, a different CPU/libc combo, a stray top-level pin)
can recur.

## Proper fix — build in CI, push to ECR, pull on EC2

### Design

| Stage | Where | What |
|---|---|---|
| Build | GitHub Actions runner (x64) | `docker buildx build --platform=linux/arm64` for both `Dockerfile` (app+worker) and `docker/nginx/Dockerfile`, using qemu/binfmt. Tag with `:${git_sha}` and `:latest`. |
| Push  | GitHub Actions → ECR        | `docker/build-push-action@v6` with ECR login. Repos: `quant-app`, `quant-nginx`. |
| Deploy | SSM Run Command on EC2     | `aws ecr get-login-password \| docker login` → `docker compose pull` → `docker compose up -d --remove-orphans`. **No build step on EC2.** |

### Benefits

- `npm ci` runs on the CI runner where the lockfile was generated → no
  EBADPLATFORM. (Or we cross-build in qemu, which has the same effect.)
- Production images are **exactly** the images CI tested.
- Deploy step is fast (pull > build) and has no compiler/toolchain on the
  prod host.
- Rollback = `docker compose pull && up -d` against the prior tag.
- Eliminates the entire class of "works on dev arch, breaks on prod arch"
  failures.

### Implementation plan

1. **ECR repos via CFN** — new stack `aws/cfn/00-ecr.yml`:
   - `quant-app` and `quant-nginx` private repos.
   - Lifecycle policy: keep last 10 tagged images, expire untagged after 1 day.
   - Add `[ecr]="00-ecr.yml"` to `STACKS` in [`aws/deploy.sh`](../../aws/deploy.sh).

2. **EC2 pull permissions** — in [`aws/cfn/03-compute.yml`](../../aws/cfn/03-compute.yml):
   - Attach `arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly` to
     the EC2 instance role.

3. **CI push permissions** — new IAM policy
   `aws/iam/github-deploy-ecr-policy.json` for the `quant_deploy` user:
   - `ecr:GetAuthorizationToken` (resource `*`).
   - `ecr:BatchCheckLayerAvailability`, `ecr:InitiateLayerUpload`,
     `ecr:UploadLayerPart`, `ecr:CompleteLayerUpload`, `ecr:PutImage`,
     `ecr:BatchGetImage` scoped to the two repo ARNs.
   - Apply via:
     ```bash
     aws iam put-user-policy --user-name quant_deploy \
       --policy-name quant-deploy-ecr \
       --policy-document file://aws/iam/github-deploy-ecr-policy.json \
       --profile alfcheun
     ```

4. **Compose wiring** — add `image:` to each service in
   [`docker-compose.yml`](../../docker-compose.yml):
   ```yaml
   api:    { image: ${APP_IMAGE:-quant-app:latest},   build: { dockerfile: Dockerfile } }
   worker: { image: ${APP_IMAGE:-quant-app:latest},   build: { dockerfile: Dockerfile } }
   nginx:  { image: ${NGINX_IMAGE:-quant-nginx:latest}, build: { context: ., dockerfile: docker/nginx/Dockerfile } }
   ```
   `APP_IMAGE` / `NGINX_IMAGE` set in [`docker-compose.prod.yml`](../../docker-compose.prod.yml)
   to the ECR URIs with `:${IMAGE_TAG}` (env var on EC2, written by deploy step).

5. **Workflow rewrite** — in [`.github/workflows/deploy.yml`](../../.github/workflows/deploy.yml):
   - Replace the standalone `build frontend` sanity job with a real
     `build-and-push` job:
     - `docker/setup-qemu-action@v3` + `docker/setup-buildx-action@v3`,
     - `aws-actions/amazon-ecr-login@v2`,
     - `docker/build-push-action@v6` × 2 (app + nginx),
       `platforms: linux/arm64`, tags `:${{ github.sha }}` and `:latest`.
   - Replace the `deploy` job's SSM commands with:
     ```
     "aws ecr get-login-password --region ap-southeast-1 | docker login --username AWS --password-stdin <acct>.dkr.ecr.ap-southeast-1.amazonaws.com",
     "cd /opt/quant",
     "git fetch ... && git reset --hard origin/main",   # for compose files only
     "IMAGE_TAG=<sha> docker compose -f docker-compose.yml -f docker-compose.prod.yml pull",
     "IMAGE_TAG=<sha> docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --remove-orphans",
     "docker image prune -f"
     ```
   - Add ECR change detection in the `cfn` job (treat `aws/cfn/00-ecr.yml`
     like the other stacks).

6. **Revert tactical workarounds** once the ECR pipeline is green:
   - `npm install` → `npm ci` in `docker/nginx/Dockerfile`.
   - Drop any qemu/buildx steps from the SSM script (no longer building on
     EC2 at all).

---

## ECR implementation checklist (file-by-file)

**Status:** adopted (decision #35) — **not yet implemented** in repo.  
**Related:** [phase-0.3-topology.md](phase-0.3-topology.md), [infrastructure.md](../architecture/infrastructure.md).

### Deploy flow — before vs after

```
TODAY:
  push main → test → (npm build check) → SSM → git pull → docker compose BUILD on EC2 → up

AFTER ECR:
  push main → test → buildx arm64 → push ECR → SSM → git pull → docker login → PULL → up
```

**Rollback:** redeploy with a previous `IMAGE_TAG=<older-git-sha>`.

---

### 1. New AWS infrastructure

**Status:** implemented in repo (step 1) — deploy manually or via CI `cfn` job before steps 2–5.

| File | Change |
|------|--------|
| **`aws/cfn/00-ecr.yml`** *(new)* | Two private repos: `quant-app`, `quant-nginx`. Lifecycle: keep last 10 tagged images; expire untagged after 1 day. Optional: scan-on-push. |
| **`aws/deploy.sh`** | Add `[ecr]="00-ecr.yml"` to `STACKS`; deploy **first** in order: `ecr` → `network` → `database` → `compute`. |
| **`aws/cfn/03-compute.yml`** | Attach managed policy `AmazonEC2ContainerRegistryReadOnly` to `Ec2Role` so EC2 can `docker pull`. |
| **`aws/iam/github-deploy-ecr-policy.json`** *(new)* | ECR push for CI user `quant_deploy`: `GetAuthorizationToken` + layer upload / `PutImage` scoped to both repo ARNs. |

**One-time ops (outside repo):**

```bash
# Deploy ECR stack
bash aws/deploy.sh ecr

# Attach push policy to GitHub deploy IAM user
aws iam put-user-policy --user-name quant_deploy \
  --policy-name quant-deploy-ecr \
  --policy-document file://aws/iam/github-deploy-ecr-policy.json \
  --profile alfcheun --region ap-southeast-1
```

---

### 2. Docker Compose

| File | Change |
|------|--------|
| **`docker-compose.yml`** | Add `image:` alongside existing `build:` (local dev still builds; prod pulls): |
| | `api` + `worker` → `${APP_IMAGE:-quant-app:latest}` |
| | `nginx` → `${NGINX_IMAGE:-quant-nginx:latest}` |
| **`docker-compose.prod.yml`** | Set ECR URIs + tag from env, e.g. `APP_IMAGE=${AWS_ACCOUNT}.dkr.ecr.ap-southeast-1.amazonaws.com/quant-app:${IMAGE_TAG}` (same pattern for `NGINX_IMAGE`). Update header comment: prod uses **`pull`**, not `--build`. |

`redis` and `certbot` stay on public Hub images — no ECR.

Future **Phase 1.7 `trade`** service reuses the **`quant-app`** ECR image with a different `command:` — no third repo.

---

### 3. GitHub Actions — `.github/workflows/deploy.yml`

| Today | After ECR |
|-------|-----------|
| `build` — npm sanity check on runner | **`build-and-push`** — builds and pushes prod images |
| `deploy` — SSM runs `docker compose build` on EC2 | **`deploy`** — SSM runs `ecr login` → `pull` → `up` only |

**New `build-and-push` job:**

- `docker/setup-qemu-action@v3` + `docker/setup-buildx-action@v3`
- `aws-actions/amazon-ecr-login@v2`
- `docker/build-push-action@v6` × 2:
  - Context `.`, `Dockerfile` → repo `quant-app`, `platforms: linux/arm64`
  - Context `.`, `docker/nginx/Dockerfile` → repo `quant-nginx`, `platforms: linux/arm64`
- Tags: `${{ github.sha }}` and `latest`

**`deploy` job — SSM commands (replace build step):**

```bash
aws ecr get-login-password --region ap-southeast-1 | \
  docker login --username AWS --password-stdin <acct>.dkr.ecr.ap-southeast-1.amazonaws.com
cd /opt/quant
git config --system --add safe.directory /opt/quant
git fetch --prune origin main && git reset --hard origin/main
export IMAGE_TAG=<git-sha>
export APP_IMAGE=<acct>.dkr.ecr.ap-southeast-1.amazonaws.com/quant-app:${IMAGE_TAG}
export NGINX_IMAGE=<acct>.dkr.ecr.ap-southeast-1.amazonaws.com/quant-nginx:${IMAGE_TAG}
docker compose -f docker-compose.yml -f docker-compose.prod.yml pull
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --remove-orphans
docker image prune -f
```

**Remove from SSM:** `docker compose … build --pull`.

**`cfn` job:** extend infra change detection to include `aws/cfn/00-ecr.yml` → deploy `ecr` stack when that file changes.

**Job graph:** `test` → `build-and-push` → `deploy`; `cfn` runs in parallel with `test` (deploy waits on both).

---

### 4. Dockerfiles

| File | Change |
|------|--------|
| **`docker/nginx/Dockerfile`** | Already uses `npm ci` — no change expected. |
| **`Dockerfile`** (app) | No change — same image for `api`, `worker`, and future `trade`. |

---

### 5. Docs and env (minor)

| File | Change |
|------|--------|
| **`docs/architecture/infrastructure.md`** | CI/CD section: build in Actions → ECR → pull on EC2 (replace “build on EC2”). |
| **`.env.example`** | Document optional `APP_IMAGE` / `NGINX_IMAGE` / `IMAGE_TAG` (set by deploy on prod, not hand-edited). |
| **`README.md`** | Prod deploy instructions if they still mention `--build`. |

---

### 6. Out of scope for this ECR slice

- ECS cluster / task definitions
- Second EC2 for TRADE (Phase 3.7 — will pull same ECR repos)
- Multi-arch images (`linux/amd64`) unless requested later — **arm64 only** for t4g Graviton
- **`t4g.medium` RAM upgrade** — separate change in `aws/params/prod.json` (Phase 0.3), can land before or after ECR cutover

---

### 7. Suggested PR / rollout order

| Step | Scope | Notes |
|------|-------|-------|
| **1** | CFN `00-ecr.yml` + EC2 ECR read on `Ec2Role` + `deploy.sh` | Deploy stack manually first |
| **2** | Compose `image:` wiring + `docker-compose.prod.yml` env | Local dev unchanged (`build` fallback) |
| **3** | GitHub workflow `build-and-push` + pull-only deploy | Cutover PR — verify one green deploy |
| **4** | IAM `github-deploy-ecr-policy.json` + manual apply | Required before step 3 can push |
| **5** | Doc touch-ups | infrastructure.md, README |

**Cutover:** single deploy to `main` replaces EC2 build with pull. Keep previous git SHA handy for rollback tag.

---

### Open questions

- Tag strategy: `:sha-<short>` + `:latest`, or also `:prod`? Probably stick to
  sha + latest; promotion is implicit on `main`.
- Do we want ARM-only images, or also amd64 for local dev on x64 laptops?
  Multi-arch (`linux/arm64,linux/amd64`) doubles build time but is cheap to
  add later.
- Image signing / scanning (ECR scan-on-push is free; cosign is a future
  consideration).

## Decision

**Adopted (Phase 0.3, revised 2026-05-20):** ECR pull deploy is **in scope now** — see decision #35 and [phase-0.3-topology.md](phase-0.3-topology.md). Implementation checklist below is the execution path; cut over from build-on-EC2 before Phase 1 Trade work ships.
