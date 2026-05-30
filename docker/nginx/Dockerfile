# Stage 1: Build React frontend
# Must be a glibc image (node:22-slim, not node:22-alpine) — Vite 7 /
# rolldown ships glibc-only bindings and fails on musl with EBADPLATFORM.
#
# The lockfile is generated cleanly from package.json (which does NOT
# hard-pin any @rolldown/binding-* package). Rolldown's per-platform
# bindings live in optionalDependencies and are flagged `"optional": true`
# in the lockfile, so `npm ci` correctly skips bindings that don't match
# the build host's (os, cpu, libc) — works on both x64 dev machines and
# arm64 (Graviton EC2).
FROM node:22-slim AS frontend-build

WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
# Dependency install only — npm audit runs in CI (tests.yml), not here, so prod
# image builds stay fast and auditable separately from the runtime artifact.
RUN npm ci --no-fund
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
