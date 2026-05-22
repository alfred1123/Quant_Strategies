#!/usr/bin/env bash
# Ensure docker compose can build (compose v2.40+ requires buildx >= 0.17.0).
# Safe to run on every deploy — no-op when a suitable buildx is already present.
set -euo pipefail

PLUGIN_DIR="/usr/local/lib/docker/cli-plugins"
BUILDX_VERSION="v0.21.2"
ARCH="$(uname -m)"
case "$ARCH" in
  aarch64) ARCH="arm64" ;;
  x86_64) ARCH="amd64" ;;
esac

mkdir -p "$PLUGIN_DIR"

buildx_ok() {
  docker buildx version >/dev/null 2>&1 || return 1
  local ver
  ver="$(docker buildx version 2>/dev/null | awk '/^github.com\/docker\/buildx/ {print $2; exit}')"
  [[ -n "$ver" ]] || ver="$(docker buildx version 2>/dev/null | grep -oE 'v[0-9]+\.[0-9]+\.[0-9]+' | head -1)"
  [[ -n "$ver" ]] || return 1
  local major minor
  major="${ver#v}"; major="${major%%.*}"
  minor="${ver#v}"; minor="${minor#*.}"; minor="${minor%%.*}"
  [[ "$major" -gt 0 ]] && return 0
  [[ "$major" -eq 0 && "$minor" -ge 17 ]]
}

if ! buildx_ok; then
  echo "Installing docker buildx ${BUILDX_VERSION} for ${ARCH}..."
  curl -fsSL \
    "https://github.com/docker/buildx/releases/download/${BUILDX_VERSION}/buildx-${BUILDX_VERSION}.linux-${ARCH}" \
    -o "${PLUGIN_DIR}/docker-buildx"
  chmod +x "${PLUGIN_DIR}/docker-buildx"
fi

docker buildx version

# Builder instance may be missing after fresh EC2 / plugin reinstall.
if ! docker buildx inspect quant-builder >/dev/null 2>&1; then
  docker buildx create --name quant-builder --use
else
  docker buildx use quant-builder
fi
