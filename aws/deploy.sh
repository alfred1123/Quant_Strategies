#!/usr/bin/env bash
# Deploy / update all CloudFormation stacks in dependency order.
#
# Usage:
#   bash aws/deploy.sh                    # deploy all stacks
#   bash aws/deploy.sh vpc                # deploy a single stack
#   bash aws/deploy.sh ec2 --dry-run      # preview changes
#
# Targets are named after the AWS service whose template they deploy (see
# STACKS); the deployed stack keeps its original name (see STACK_SUFFIX).
#
# Requires: AWS CLI v2 with a valid SSO session or access keys.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PARAMS_DIR="${SCRIPT_DIR}/params"

PROJECT="${PROJECT:-quant}"
ENV="${APP_ENV:-prod}"
REGION="${AWS_REGION:-ap-southeast-1}"
PARAMS_FILE="${PARAMS_DIR}/${ENV}.json"

DRY_RUN=false
if [[ "${*}" == *"--dry-run"* ]]; then
  DRY_RUN=true
fi

# ── Stack definitions ─────────────────────────────────────────────────
# Templates live under cfn/<service>/: the folder tells you what a template
# creates without opening it, and CloudFormation input stays clear of params/
# and scripts/, which are kinds of file rather than AWS services. Dependency
# order is ORDERED below, not a filename prefix.
declare -A STACKS=(
  [ecr]="cfn/ecr/image-repositories.yml"
  [vpc]="cfn/vpc/security-groups.yml"
  [database]="cfn/database/aurora-cluster.yml"
  [ec2]="cfn/ec2/app-host.yml"
  [eventbridge]="cfn/eventbridge/scheduled-task.yml"
  [uk-egress]="cfn/ec2/uk-egress-proxy.yml"
)

# Target name → live CloudFormation stack suffix, where they differ. These
# stacks exist in prod and CloudFormation identifies them **by name**: a stack
# is not renamed by renaming it here, it is replaced by a new empty one while
# the real resources are orphaned. So the folders follow AWS service names and
# the deployed names stay frozen.
declare -A STACK_SUFFIX=(
  [vpc]="network"
  [ec2]="compute"
  [eventbridge]="scheduler"
)

# uk-egress is absent on purpose: it lives in eu-west-2, and a bare
# `deploy.sh` runs everything against one REGION. Deploy it by name:
#   AWS_REGION=eu-west-2 bash aws/deploy.sh uk-egress
ORDERED=(ecr vpc database ec2 eventbridge)

LAMBDA_SCHEDULED_TASK_DIR="${SCRIPT_DIR}/lambda/scheduled-task"
LAMBDA_SCHEDULED_TASK_NAME="${PROJECT}-scheduled-task"

deploy_stack() {
  local name="$1"
  local template="${SCRIPT_DIR}/${STACKS[$name]}"
  local stack_name="${PROJECT}-${STACK_SUFFIX[$name]:-$name}"

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
        overrides+=("${key}=${val}")
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
      override_args+=("MasterUserPassword=${db_pw}")
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
      override_args+=("RdsSecurityGroupId=${rds_sg}")
    fi
  fi

  if [[ "$name" == "ec2" ]]; then
    local ec2_sg ec2_rds_sg
    ec2_sg=$(aws cloudformation describe-stacks \
      --stack-name "${PROJECT}-network" \
      --query "Stacks[0].Outputs[?OutputKey=='Ec2SecurityGroupId'].OutputValue" \
      --output text --region "$REGION" --no-cli-pager 2>/dev/null || true)
    if [[ -n "$ec2_sg" ]]; then
      override_args+=("Ec2SecurityGroupId=${ec2_sg}")
    fi
  fi

  if [[ "$name" == "eventbridge" ]]; then
    local token_path="/quant/${ENV}/TRADE_SERVICE_TOKEN"
    if ! aws ssm get-parameter --name "$token_path" --region "$REGION" \
         --no-cli-pager >/dev/null 2>&1; then
      echo "ERROR: SSM parameter ${token_path} is required before deploying scheduler."
      echo "  Create it with:"
      echo "    bash aws/scripts/init-ssm-params.sh"
      echo "  or:"
      echo "    aws ssm put-parameter --name ${token_path} \\"
      echo "      --value \"\$(openssl rand -base64 32)\" --type SecureString \\"
      echo "      --region ${REGION}"
      return 1
    fi

    # sync_schedules.py runs under system python3, not the repo virtualenv, so
    # having these in env/ is not enough. Checked here rather than at the sync
    # call so the run stops before CloudFormation, instead of leaving a fresh
    # stack whose schedules were never created.
    if ! python3 -c "import boto3, yaml" >/dev/null 2>&1; then
      echo "ERROR: python3 cannot import boto3 and pyyaml, both needed to sync schedules."
      echo "  Install them for the interpreter on PATH:"
      echo "    python3 -m pip install boto3 pyyaml"
      return 1
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

  if [[ "$name" == "eventbridge" ]]; then
    upload_scheduled_task_lambda
    sync_schedules
  fi
}

upload_scheduled_task_lambda() {
  local handler="${LAMBDA_SCHEDULED_TASK_DIR}/handler.py"
  local zip_dir zip_path
  # A temp *directory*: mktemp on a file leaves a 0-byte one behind, and an
  # archiver handed an existing path treats it as an archive to update, so
  # packaging died with "Zip file structure invalid" the first time this ran.
  zip_dir="$(mktemp -d)"
  zip_path="${zip_dir}/handler.zip"

  if [[ ! -f "$handler" ]]; then
    echo "ERROR: Lambda handler not found: ${handler}"
    return 1
  fi

  echo "  Packaging Lambda from ${LAMBDA_SCHEDULED_TASK_DIR} ..."
  # python3 rather than `zip`, which is not installed everywhere (and is one
  # more thing to install on a runner); this script already requires python3.
  # Running from the handler's directory keeps it at the archive root, which is
  # where the `handler.handler` entry point looks for it.
  (
    cd "${LAMBDA_SCHEDULED_TASK_DIR}"
    python3 -m zipfile -c "${zip_path}" handler.py
  )

  echo "  Uploading code → ${LAMBDA_SCHEDULED_TASK_NAME}"
  aws lambda update-function-code \
    --function-name "${LAMBDA_SCHEDULED_TASK_NAME}" \
    --zip-file "fileb://${zip_path}" \
    --region "$REGION" \
    --no-cli-pager \
    --query '{FunctionName:FunctionName,LastUpdateStatus:LastUpdateStatus,CodeSize:CodeSize}' \
    --output table

  rm -rf "${zip_dir}"
  echo "  ✓ Lambda code updated."
}

sync_schedules() {
  local sync_script="${SCRIPT_DIR}/../scripts/sync_schedules.py"
  if [[ ! -f "$sync_script" ]]; then
    echo "  WARN: sync_schedules.py not found — skipping schedule sync."
    return 0
  fi

  echo "  Syncing EventBridge schedules from config/scheduler/ ..."
  local flags=()
  if $DRY_RUN; then
    flags+=(--dry-run)
  fi
  python3 "$sync_script" "${flags[@]}"
  echo "  ✓ Schedule sync complete."
}

# ── Main ──────────────────────────────────────────────────────────────
TARGET="${1:-all}"
# A bare flag is not a stack name: `deploy.sh --dry-run` previews everything,
# where treating the flag as the target strips it to "" and trips `set -u` on
# the empty STACKS subscript.
[[ "$TARGET" == --* ]] && TARGET="all"

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
    echo "Unknown stack: ${TARGET}.  Available: ${!STACKS[*]}"
    exit 1
  fi
  deploy_stack "$TARGET"
fi

echo ""
echo "══════════════════════════════════════════════════════════"
echo "  All done."
echo "══════════════════════════════════════════════════════════"
