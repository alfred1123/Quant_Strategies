# Stage 1: Build React frontend
# NOTE: must be a glibc image (node:22-slim, not node:22-alpine) — Vite 7 /
# rolldown ships @rolldown/binding-linux-x64-gnu which is glibc-only and
# fails on musl with EBADPLATFORM.
#
# We deliberately do NOT copy package-lock.json. The lockfile pins
# @rolldown/binding-linux-x64-gnu as a materialized node_modules entry
# without the `"optional": true` flag (npm/cli#4828), so both `npm ci`
# and `npm install` (which honors the lockfile when present) treat it as
# required and fail on arm64 (Graviton EC2) with EBADPLATFORM.
# Installing from package.json only lets npm re-resolve rolldown's
# optionalDependencies against the current platform and pick the correct
# binding. Trade-off: not bit-for-bit reproducible.
# Long-term fix: build images in CI, push to ECR.
# See docs/design/deploy-build-pipeline.md.
FROM node:22-slim AS frontend-build

WORKDIR /app
COPY frontend/package.json ./
RUN npm install --no-audit --no-fund
# Copy the rest of the frontend tree. node_modules is already populated
# with arch-correct bindings; any lockfile copied in here is unused by
# `npm run build`.
COPY frontend/ .
RUN npm run build

# Stage 2: nginx with built frontend
FROM nginx:1.27-alpine

RUN rm /etc/nginx/conf.d/default.conf

# HTTP-only config baked in (works out of the box for local dev).
# Production mounts the TLS config as a volume override.
COPY docker/nginx/nginx.dev.conf /etc/nginx/nginx.conf

COPY --from=frontend-build /app/dist /usr/share/nginx/html

RUN mkdir -p /var/www/certbot

EXPOSE 80 443
