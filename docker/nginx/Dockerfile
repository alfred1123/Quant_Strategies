# Stage 1: Build React frontend
# NOTE: must be a glibc image (node:22-slim, not node:22-alpine) — Vite 7 /
# rolldown ships @rolldown/binding-linux-x64-gnu which is glibc-only and
# fails `npm ci` on musl with EBADPLATFORM.
#
# The lockfile is regenerated with multi-arch optional native deps via:
#   cd frontend && rm -rf node_modules package-lock.json
#   npm install --force --os=linux --cpu=x64 --os=linux --cpu=arm64
# so `npm ci` picks the correct rolldown binding on both x64 dev machines
# and arm64 (Graviton) build hosts.
# Stage 1: Build React frontend
# NOTE: must be a glibc image (node:22-slim, not node:22-alpine) — Vite 7 /
# rolldown ships @rolldown/binding-linux-x64-gnu which is glibc-only and
# fails `npm ci` on musl with EBADPLATFORM.
#
# Pinned to linux/amd64 because:
#   1. The lockfile materializes @rolldown/binding-linux-x64-gnu as a
#      required entry (npm strips `"optional": true` from selected
#      bindings during install), so `npm ci` fails on any non-x64 host
#      regardless of npm version. See npm/cli#4828.
#   2. The frontend output is static HTML/JS/CSS — arch-agnostic — so
#      building under x86 emulation on arm64 EC2 (Graviton) is safe.
#      Emulation adds ~1-2 min to this stage but avoids the npm bug
#      entirely and keeps deterministic `npm ci`.
FROM --platform=linux/amd64 node:22-slim AS frontend-build

WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
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
