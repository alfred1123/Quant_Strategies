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

1. Vite 7 uses **rolldown**, which ships per-platform native bindings
   (`@rolldown/binding-linux-{x64,arm64}-{gnu,musl}`, `darwin-*`, `win32-*`)
   as `optionalDependencies` on the `rolldown` package.
2. `package-lock.json` materializes the bindings as explicit
   `node_modules/...` entries. **npm strips the `"optional": true` flag
   from these materialized entries** (npm/cli#4828), so `npm ci`
   treats them as required and fails on any host whose `(os, cpu, libc)`
   doesn't match a binding present in the lockfile.
3. Our lockfile was generated on x64-glibc, so it pins
   `@rolldown/binding-linux-x64-gnu`. Building on arm64 Graviton → EBADPLATFORM.
4. **`npm ci` is fundamentally broken for this case**, regardless of:
   - npm version (verified npm 10 and npm 11),
   - regenerating a multi-arch lockfile (`npm install --os=linux --cpu=x64 --cpu=arm64`) — the bindings are still listed without the optional flag,
   - alpine vs slim base image (musl vs glibc swap only changes which binding is missing).

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

In [`docker/nginx/Dockerfile`](../../docker/nginx/Dockerfile):

```dockerfile
FROM node:22-slim AS frontend-build
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm install --no-audit --no-fund
```

- Switched from `npm ci` → `npm install`. `install` re-resolves optional deps
  for the current platform at install time, so it picks the correct rolldown
  binding for whichever arch is building.
- Trade-offs:
  - **Not bit-for-bit reproducible** — lockfile is no longer authoritative.
  - Slightly slower than `npm ci`.
  - Still builds on the EC2 host, so future native-deps surprises are still
    possible.

This unblocks deploys today. It is **not the proper fix**.

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

### Open questions

- Tag strategy: `:sha-<short>` + `:latest`, or also `:prod`? Probably stick to
  sha + latest; promotion is implicit on `main`.
- Do we want ARM-only images, or also amd64 for local dev on x64 laptops?
  Multi-arch (`linux/arm64,linux/amd64`) doubles build time but is cheap to
  add later.
- Image signing / scanning (ECR scan-on-push is free; cosign is a future
  consideration).

## Decision

Documenting here for now; not yet adopted as a numbered entry in
[decisions.md](../decisions.md). Promote once the ECR pipeline lands.
