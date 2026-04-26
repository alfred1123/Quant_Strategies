# Stage 1: Build React frontend
FROM node:22-alpine AS frontend-build

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
