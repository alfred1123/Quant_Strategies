#!/usr/bin/env bash
# Deploy / update all CloudFormation stacks in dependency order.
#
# Usage:
#   bash aws/deploy.sh                    # deploy all stacks
#   bash aws/deploy.sh network            # deploy a single stack
#   bash aws/deploy.sh compute --dry-run  # preview changes
#
# Requires: AWS CLI v2 with a valid SSO session or access keys.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CFN_DIR="${SCRIPT_DIR}/cfn"
PARAMS_DIR="${SCRIPT_DIR}/params"

PROJECT="${PROJECT:-quant}"
ENV="${APP_ENV:-prod}"
REGION="${AWS_REGION:-ap-southeast-1}"
PARAMS_FILE="${PARAMS_DIR}/${ENV}.json"

DRY_RUN=false
if [[ "${*}" == *"--dry-run"* ]]; then
  DRY_RUN=true
fi

# ── Stack definitions (order matters) ─────────────────────────────────
declare -A STACKS=(
  [network]="01-network.yml"
  [database]="02-database.yml"
  [compute]="03-compute.yml"
)
ORDERED=(network database compute)

deploy_stack() {
  local name="$1"
  local template="${CFN_DIR}/${STACKS[$name]}"
  local stack_name="${PROJECT}-${name}"

  echo ""
  echo "══════════════════════════════════════════════════════════"
  echo "  Stack: ${stack_name}  (${template})"
  echo "══════════════════════════════════════════════════════════"

  if [[ ! -f "$template" ]]; then
    echo "ERROR: template not found: ${template}"
    return 1
  fi

  # Validate first
  aws cloudformation validate-template \
    --template-body "file://${template}" \
    --region "$REGION" \
    --no-cli-pager >/dev/null
  echo "  Template valid."

  if $DRY_RUN; then
    echo "  DRY RUN — skipping deploy."
    return 0
  fi

  # Build parameter overrides from the params file.
  # Filter to only parameters the template actually declares.
  local template_params
  template_params=$(aws cloudformation validate-template \
    --template-body "file://${template}" \
    --region "$REGION" \
    --query 'Parameters[*].ParameterKey' \
    --output text --no-cli-pager)

  local overrides=()
  if [[ -f "$PARAMS_FILE" ]]; then
    for key in $template_params; do
      local val
      val=$(python3 -c "
import json, sys
params = json.load(open('${PARAMS_FILE}'))
matches = [p['ParameterValue'] for p in params if p['ParameterKey'] == '${key}']
print(matches[0] if matches else '', end='')
" 2>/dev/null || true)
      if [[ -n "$val" ]]; then
        overrides+=("ParameterKey=${key},ParameterValue=${val}")
      fi
    done
  fi

  local override_args=()
  if [[ ${#overrides[@]} -gt 0 ]]; then
    override_args=(--parameter-overrides "${overrides[@]}")
  fi

  # For database stack, prompt for master password if not in params
  if [[ "$name" == "database" ]]; then
    local has_pw=false
    for o in "${overrides[@]:-}"; do
      [[ "$o" == *MasterUserPassword* ]] && has_pw=true
    done
    if ! $has_pw; then
      read -rsp "  DB master password (or Ctrl-C to abort): " db_pw; echo
      override_args+=("ParameterKey=MasterUserPassword,ParameterValue=${db_pw}")
    fi
  fi

  # Cross-stack references: inject exported values from prior stacks.
  if [[ "$name" == "database" ]]; then
    local rds_sg
    rds_sg=$(aws cloudformation describe-stacks \
      --stack-name "${PROJECT}-network" \
      --query "Stacks[0].Outputs[?OutputKey=='RdsSecurityGroupId'].OutputValue" \
      --output text --region "$REGION" --no-cli-pager 2>/dev/null || true)
    if [[ -n "$rds_sg" ]]; then
      override_args+=("ParameterKey=RdsSecurityGroupId,ParameterValue=${rds_sg}")
    fi
  fi

  if [[ "$name" == "compute" ]]; then
    local ec2_sg ec2_rds_sg
    ec2_sg=$(aws cloudformation describe-stacks \
      --stack-name "${PROJECT}-network" \
      --query "Stacks[0].Outputs[?OutputKey=='Ec2SecurityGroupId'].OutputValue" \
      --output text --region "$REGION" --no-cli-pager 2>/dev/null || true)
    if [[ -n "$ec2_sg" ]]; then
      override_args+=("ParameterKey=Ec2SecurityGroupId,ParameterValue=${ec2_sg}")
    fi
  fi

  aws cloudformation deploy \
    --template-file "$template" \
    --stack-name "$stack_name" \
    --capabilities CAPABILITY_NAMED_IAM \
    --region "$REGION" \
    --no-fail-on-empty-changeset \
    --no-cli-pager \
    "${override_args[@]}" \
    --tags "Project=${PROJECT}" "Environment=${ENV}"

  echo "  ✓ ${stack_name} deployed."
}

# ── Main ──────────────────────────────────────────────────────────────
TARGET="${1:-all}"

echo "Deploying project=${PROJECT}  env=${ENV}  region=${REGION}"
echo "Params file: ${PARAMS_FILE}"

if [[ "$TARGET" == "all" ]]; then
  for name in "${ORDERED[@]}"; do
    deploy_stack "$name"
  done
else
  # Strip --dry-run from target
  TARGET="${TARGET/--dry-run/}"
  TARGET="${TARGET// /}"
  if [[ -z "${STACKS[$TARGET]+x}" ]]; then
    echo "Unknown stack: ${TARGET}.  Available: ${ORDERED[*]}"
    exit 1
  fi
  deploy_stack "$TARGET"
fi

echo ""
echo "══════════════════════════════════════════════════════════"
echo "  All done."
echo "══════════════════════════════════════════════════════════"
