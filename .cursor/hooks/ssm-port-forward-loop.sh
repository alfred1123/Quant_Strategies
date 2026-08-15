#!/usr/bin/env bash
# Background reconnect loop: tunnels RDS quantdb-cluster:5432 to localhost:5433 via SSM.
# Restarts the SSM session whenever it exits, with a 5s back-off.
# Launched detached by .cursor/hooks/ssm-port-forward.sh.
#
# The target instance is resolved by tag on every attempt rather than hardcoded —
# CloudFormation replaces the instance on stack updates, which changes its ID.

set -uo pipefail

TAG_NAME="quant-server"
TAG_PROJECT="quant"
RDS_HOST="quantdb-cluster.cluster-c2pnphmnxjwr.ap-southeast-1.rds.amazonaws.com"
REMOTE_PORT="5432"
LOCAL_PORT="5433"
AWS_PROFILE_NAME="alfcheun"
AWS_REGION_NAME="${AWS_REGION:-ap-southeast-1}"

PARAMS=$(printf '{"host":["%s"],"portNumber":["%s"],"localPortNumber":["%s"]}' \
  "$RDS_HOST" "$REMOTE_PORT" "$LOCAL_PORT")

log() { echo "[$(date '+%F %T')] $*"; }

cleanup() {
  log "received signal, exiting reconnect loop."
  exit 0
}
trap cleanup INT TERM

# A second forwarder on the same port produces a tunnel that listens but refuses
# connections, so yield instead of competing.
port_is_served() {
  timeout 2 bash -c "cat < /dev/null > /dev/tcp/127.0.0.1/${LOCAL_PORT}" 2>/dev/null
}

resolve_instance() {
  aws ec2 describe-instances \
    --filters "Name=tag:Name,Values=${TAG_NAME}" \
              "Name=tag:Project,Values=${TAG_PROJECT}" \
              "Name=instance-state-name,Values=running" \
    --query 'Reservations[].Instances[0].InstanceId' \
    --output text \
    --profile "$AWS_PROFILE_NAME" \
    --region "$AWS_REGION_NAME" 2>/dev/null
}

while true; do
  if port_is_served; then
    log "local:${LOCAL_PORT} already served by another forwarder; waiting."
    sleep 30
    continue
  fi

  target="$(resolve_instance)"
  if [[ -z "$target" || "$target" == "None" ]]; then
    log "no running instance tagged Name=${TAG_NAME},Project=${TAG_PROJECT}. Retrying in 30s..."
    sleep 30
    continue
  fi

  log "Starting SSM port-forward via ${target} (local:$LOCAL_PORT -> $RDS_HOST:$REMOTE_PORT)..."
  aws ssm start-session \
    --target "$target" \
    --document-name AWS-StartPortForwardingSessionToRemoteHost \
    --parameters "$PARAMS" \
    --profile "$AWS_PROFILE_NAME" \
    --region "$AWS_REGION_NAME"
  rc=$?
  log "SSM session ended (exit $rc). Reconnecting in 5s..."
  sleep 5
done
