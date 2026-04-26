#!/usr/bin/env bash
# Background reconnect loop: tunnels RDS quantdb-cluster:5432 to localhost:5433 via SSM.
# Restarts the SSM session whenever it exits, with a 5s back-off.
# Launched detached by .cursor/hooks/ssm-port-forward.sh.

set -uo pipefail

TARGET_INSTANCE="i-096f85bf84852cce3"
RDS_HOST="quantdb-cluster.cluster-c2pnphmnxjwr.ap-southeast-1.rds.amazonaws.com"
REMOTE_PORT="5432"
LOCAL_PORT="5433"
AWS_PROFILE_NAME="loki99-art"

PARAMS=$(printf '{"host":["%s"],"portNumber":["%s"],"localPortNumber":["%s"]}' \
  "$RDS_HOST" "$REMOTE_PORT" "$LOCAL_PORT")

cleanup() {
  echo "[$(date '+%F %T')] received signal, exiting reconnect loop."
  exit 0
}
trap cleanup INT TERM

while true; do
  echo "[$(date '+%F %T')] Starting SSM port-forward (local:$LOCAL_PORT -> $RDS_HOST:$REMOTE_PORT)..."
  aws ssm start-session \
    --target "$TARGET_INSTANCE" \
    --document-name AWS-StartPortForwardingSessionToRemoteHost \
    --parameters "$PARAMS" \
    --profile "$AWS_PROFILE_NAME"
  rc=$?
  echo "[$(date '+%F %T')] SSM session ended (exit $rc). Reconnecting in 5s..."
  sleep 5
done
