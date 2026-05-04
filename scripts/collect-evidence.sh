#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TF_DIR="$ROOT/terraform"

: "${AWS_PROFILE:?Set AWS_PROFILE to your AWS CLI profile}"
: "${AWS_REGION:=us-east-2}"

require_command() {
  local name="$1"
  if ! command -v "$name" >/dev/null 2>&1; then
    echo "missing required command: $name" >&2
    exit 1
  fi
}

write_json_status() {
  local path="$1"
  local status="$2"
  local detail="$3"
  jq -n \
    --arg status "$status" \
    --arg detail "$detail" \
    --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    '{status: $status, detail: $detail, collected_at: $ts}' > "$path"
}

require_command aws
require_command jq
require_command terraform

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
out_dir="$ROOT/evidence/$timestamp"
mkdir -p "$out_dir"

cd "$TF_DIR"
terraform output -json > "$out_dir/terraform-outputs.json"

instance_id="$(terraform output -raw instance_id)"
dashboard_name="$(terraform output -raw cloudwatch_dashboard_name 2>/dev/null || true)"
guardduty_detector_id="$(terraform output -raw guardduty_detector_id 2>/dev/null || true)"
agent_audit_kms_key_arn="$(terraform output -raw agent_audit_kms_key_arn 2>/dev/null || true)"
agent_audit_log_group_name="$(terraform output -raw agent_audit_log_group_name 2>/dev/null || true)"

aws sts get-caller-identity \
  --profile "$AWS_PROFILE" \
  --region "$AWS_REGION" > "$out_dir/aws-caller-identity.json"

aws ec2 describe-instances \
  --profile "$AWS_PROFILE" \
  --region "$AWS_REGION" \
  --instance-ids "$instance_id" > "$out_dir/ec2-instance.json"

security_group_ids=()
while IFS= read -r security_group_id; do
  if [[ -n "$security_group_id" ]]; then
    security_group_ids+=("$security_group_id")
  fi
done < <(jq -r '.Reservations[].Instances[].SecurityGroups[].GroupId' "$out_dir/ec2-instance.json")
if ((${#security_group_ids[@]} > 0)); then
  aws ec2 describe-security-groups \
    --profile "$AWS_PROFILE" \
    --region "$AWS_REGION" \
    --group-ids "${security_group_ids[@]}" > "$out_dir/security-groups.json"
else
  write_json_status "$out_dir/security-groups.json" "missing" "No security groups found for instance $instance_id"
fi

aws ssm describe-instance-information \
  --profile "$AWS_PROFILE" \
  --region "$AWS_REGION" \
  --filters "Key=InstanceIds,Values=$instance_id" > "$out_dir/ssm-instance-information.json"

if [[ -n "$guardduty_detector_id" ]]; then
  aws guardduty get-detector \
    --profile "$AWS_PROFILE" \
    --region "$AWS_REGION" \
    --detector-id "$guardduty_detector_id" > "$out_dir/guardduty-detector.json"
else
  write_json_status "$out_dir/guardduty-detector.json" "missing" "Terraform output guardduty_detector_id was empty"
fi

if [[ -n "$dashboard_name" ]]; then
  aws cloudwatch get-dashboard \
    --profile "$AWS_PROFILE" \
    --region "$AWS_REGION" \
    --dashboard-name "$dashboard_name" > "$out_dir/cloudwatch-dashboard.json"
else
  write_json_status "$out_dir/cloudwatch-dashboard.json" "missing" "Terraform output cloudwatch_dashboard_name was empty"
fi

if [[ -n "$agent_audit_kms_key_arn" ]]; then
  aws kms describe-key \
    --profile "$AWS_PROFILE" \
    --region "$AWS_REGION" \
    --key-id "$agent_audit_kms_key_arn" > "$out_dir/agent-audit-kms-key.json"
else
  write_json_status "$out_dir/agent-audit-kms-key.json" "missing" "Terraform output agent_audit_kms_key_arn was empty"
fi

if [[ -n "$agent_audit_log_group_name" ]]; then
  aws logs describe-log-groups \
    --profile "$AWS_PROFILE" \
    --region "$AWS_REGION" \
    --log-group-name-prefix "$agent_audit_log_group_name" > "$out_dir/agent-audit-log-group.json"
  aws logs describe-log-streams \
    --profile "$AWS_PROFILE" \
    --region "$AWS_REGION" \
    --log-group-name "$agent_audit_log_group_name" \
    --order-by LastEventTime \
    --descending \
    --max-items 5 > "$out_dir/agent-audit-log-streams.json"
  latest_stream="$(jq -r '.logStreams[0].logStreamName // ""' "$out_dir/agent-audit-log-streams.json")"
  if [[ -n "$latest_stream" ]]; then
    aws logs get-log-events \
      --profile "$AWS_PROFILE" \
      --region "$AWS_REGION" \
      --log-group-name "$agent_audit_log_group_name" \
      --log-stream-name "$latest_stream" \
      --limit 20 > "$out_dir/agent-audit-log-events.json"
  else
    write_json_status "$out_dir/agent-audit-log-events.json" "empty" "No agent audit log streams exist yet"
  fi
else
  write_json_status "$out_dir/agent-audit-log-group.json" "missing" "Terraform output agent_audit_log_group_name was empty"
  write_json_status "$out_dir/agent-audit-log-streams.json" "missing" "Terraform output agent_audit_log_group_name was empty"
  write_json_status "$out_dir/agent-audit-log-events.json" "missing" "Terraform output agent_audit_log_group_name was empty"
fi

cd "$ROOT"
fetch_status="ok"
if ! ./scripts/fetch-logs.sh > "$out_dir/fetch-logs.out" 2>&1; then
  fetch_status="failed"
fi

if [[ -f "$ROOT/logs/zt-verify.json" ]]; then
  cp "$ROOT/logs/zt-verify.json" "$out_dir/zt-verify.json"
  jq empty "$out_dir/zt-verify.json"
else
  write_json_status "$out_dir/zt-verify.json" "missing" "logs/zt-verify.json was not available after fetch-logs"
fi

policy_status="ok"
if ! make policy > "$out_dir/policy.out" 2>&1; then
  policy_status="failed"
fi

jq -n \
  --arg project "zt-infra-v2" \
  --arg region "$AWS_REGION" \
  --arg profile "$AWS_PROFILE" \
  --arg instance_id "$instance_id" \
  --arg guardduty_detector_id "$guardduty_detector_id" \
  --arg cloudwatch_dashboard_name "$dashboard_name" \
  --arg agent_audit_kms_key_arn "$agent_audit_kms_key_arn" \
  --arg agent_audit_log_group_name "$agent_audit_log_group_name" \
  --arg fetch_status "$fetch_status" \
  --arg policy_status "$policy_status" \
  --arg collected_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  '{
    project: $project,
    collected_at: $collected_at,
    aws_region: $region,
    aws_profile: $profile,
    instance_id: $instance_id,
    guardduty_detector_id: $guardduty_detector_id,
    cloudwatch_dashboard_name: $cloudwatch_dashboard_name,
    agent_audit_kms_key_arn: $agent_audit_kms_key_arn,
    agent_audit_log_group_name: $agent_audit_log_group_name,
    checks: {
      fetch_logs: $fetch_status,
      policy: $policy_status
    },
    files: [
      "terraform-outputs.json",
      "aws-caller-identity.json",
      "ec2-instance.json",
      "security-groups.json",
      "ssm-instance-information.json",
      "guardduty-detector.json",
      "cloudwatch-dashboard.json",
      "agent-audit-kms-key.json",
      "agent-audit-log-group.json",
      "agent-audit-log-streams.json",
      "agent-audit-log-events.json",
      "zt-verify.json",
      "fetch-logs.out",
      "policy.out"
    ]
  }' > "$out_dir/manifest.json"

if [[ "$fetch_status" != "ok" || "$policy_status" != "ok" ]]; then
  echo "evidence collected with failures: $out_dir" >&2
  exit 1
fi

echo "evidence collected: $out_dir"
