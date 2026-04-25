#!/usr/bin/env bash
# Apply (create or update) the main-branch ruleset for this repo.
#
# Requirements:
#   - GITHUB_TOKEN env var with a fine-grained PAT having
#     "Administration: Read and write" on this repo.
#
# Usage:
#   export GITHUB_TOKEN=ghp_xxx
#   ./scripts/branch-protection/apply.sh
#
# Idempotent: if a ruleset named "main protection" already exists, it
# is updated in place; otherwise a new one is created.

set -euo pipefail

OWNER="alfred1123"
REPO="Quant_Strategies"
NAME="main protection"
PAYLOAD="$(dirname "$0")/ruleset-main.json"

: "${GITHUB_TOKEN:?Set GITHUB_TOKEN with a PAT having Administration: write}"

API="https://api.github.com/repos/${OWNER}/${REPO}/rulesets"
HDR_AUTH="Authorization: Bearer ${GITHUB_TOKEN}"
HDR_ACCEPT="Accept: application/vnd.github+json"
HDR_API="X-GitHub-Api-Version: 2022-11-28"

# Find existing ruleset id by name.
existing_id="$(
  curl -fsSL -H "$HDR_AUTH" -H "$HDR_ACCEPT" -H "$HDR_API" "$API" |
  python3 -c "import json,sys; rs=json.load(sys.stdin); print(next((r['id'] for r in rs if r['name']=='${NAME}'), ''))"
)"

if [[ -n "$existing_id" ]]; then
  echo "Updating ruleset id=$existing_id"
  curl -fsSL -X PUT \
    -H "$HDR_AUTH" -H "$HDR_ACCEPT" -H "$HDR_API" \
    "${API}/${existing_id}" \
    --data @"$PAYLOAD" | python3 -m json.tool | head -40
else
  echo "Creating new ruleset '${NAME}'"
  curl -fsSL -X POST \
    -H "$HDR_AUTH" -H "$HDR_ACCEPT" -H "$HDR_API" \
    "$API" \
    --data @"$PAYLOAD" | python3 -m json.tool | head -40
fi

echo "Done."
