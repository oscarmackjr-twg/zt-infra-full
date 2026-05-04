#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/terraform"

: "${AWS_PROFILE:?Set AWS_PROFILE to your AWS CLI profile}"
: "${AWS_REGION:=us-east-2}"
: "${FETCH_LOG_LINES:=160}"
: "${SSM_WAIT_ATTEMPTS:=40}"
: "${SSM_WAIT_SECONDS:=5}"
: "${VERIFY_WAIT_ATTEMPTS:=60}"
: "${VERIFY_WAIT_SECONDS:=5}"

INSTANCE_ID="$(terraform output -raw instance_id)"
mkdir -p "$ROOT/logs"

wait_for_ssm() {
  local n=1
  local ping=""
  while (( n <= SSM_WAIT_ATTEMPTS )); do
    ping="$(aws ssm describe-instance-information \
      --profile "$AWS_PROFILE" \
      --region "$AWS_REGION" \
      --filters "Key=InstanceIds,Values=$INSTANCE_ID" \
      --query 'InstanceInformationList[0].PingStatus' \
      --output text 2>/dev/null || true)"
    if [[ "$ping" == "Online" ]]; then
      return 0
    fi
    echo "waiting for SSM on $INSTANCE_ID ($n/$SSM_WAIT_ATTEMPTS; status=${ping:-missing})"
    sleep "$SSM_WAIT_SECONDS"
    n=$((n + 1))
  done
  echo "SSM did not become Online for $INSTANCE_ID" >&2
  return 1
}

run_ssm_command() {
  local name="$1"
  local command="$2"
  local command_id

  command_id="$(aws ssm send-command \
    --profile "$AWS_PROFILE" \
    --region "$AWS_REGION" \
    --instance-ids "$INSTANCE_ID" \
    --document-name AWS-RunShellScript \
    --parameters "commands=$command" \
    --query 'Command.CommandId' \
    --output text)"

  aws ssm wait command-executed \
    --profile "$AWS_PROFILE" \
    --region "$AWS_REGION" \
    --command-id "$command_id" \
    --instance-id "$INSTANCE_ID"

  aws ssm get-command-invocation \
    --profile "$AWS_PROFILE" \
    --region "$AWS_REGION" \
    --command-id "$command_id" \
    --instance-id "$INSTANCE_ID" \
    --query 'StandardOutputContent' \
    --output text | tee "$ROOT/logs/$name"
}

wait_for_ssm
run_ssm_command "zt-bootstrap.log" "sudo tail -n $FETCH_LOG_LINES /var/log/zt-bootstrap.log"
run_ssm_command "zt-verify.json" "n=1; while test \$n -le $VERIFY_WAIT_ATTEMPTS; do if sudo test -s /var/log/zt-verify.json; then sudo cat /var/log/zt-verify.json; exit 0; fi; echo waiting for /var/log/zt-verify.json \$n/$VERIFY_WAIT_ATTEMPTS; sleep $VERIFY_WAIT_SECONDS; n=\$((n + 1)); done; echo /var/log/zt-verify.json was not generated >&2; exit 1"
