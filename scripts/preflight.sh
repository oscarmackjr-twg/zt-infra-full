#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
: "${AWS_PROFILE:?Set AWS_PROFILE to your AWS CLI profile}"
: "${AWS_REGION:=us-east-2}"
: "${TAILSCALE_SECRET_NAME:?Set TAILSCALE_SECRET_NAME to your AWS Secrets Manager secret name}"
command -v terraform >/dev/null || { echo "terraform missing"; exit 2; }
command -v aws >/dev/null || { echo "aws cli missing"; exit 2; }
command -v python3 >/dev/null || { echo "python3 missing"; exit 2; }
aws sts get-caller-identity --profile "$AWS_PROFILE" --region "$AWS_REGION" >/dev/null

validate_tailscale_auth_key() {
  local auth_key="$1"
  if [[ ! "$auth_key" =~ ^tskey-auth-[A-Za-z0-9]+-[A-Za-z0-9]+$ ]]; then
    cat >&2 <<MSG
Tailscale auth key format is invalid.

Expected a key shaped like:
  tskey-auth-...-...

Rotate the secret without printing the key in logs:
  ./scripts/create-tailscale-secret.sh '$TAILSCALE_SECRET_NAME' 'tskey-auth-REPLACE_ME'
MSG
    exit 4
  fi
}

ensure_tailscale_secret() {
  if aws secretsmanager describe-secret --secret-id "$TAILSCALE_SECRET_NAME" --profile "$AWS_PROFILE" --region "$AWS_REGION" >/dev/null 2>&1; then
    local current_secret
    current_secret="$(aws secretsmanager get-secret-value \
      --secret-id "$TAILSCALE_SECRET_NAME" \
      --query SecretString \
      --output text \
      --profile "$AWS_PROFILE" \
      --region "$AWS_REGION")"
    validate_tailscale_auth_key "$current_secret"
    return 0
  fi

  local auth_key="${TAILSCALE_AUTH_KEY:-}"
  if [[ -z "$auth_key" && -f "$ROOT/tailscale-auth-key" ]]; then
    auth_key="$(<"$ROOT/tailscale-auth-key")"
  fi

  if [[ -n "$auth_key" ]]; then
    validate_tailscale_auth_key "$auth_key"
    aws secretsmanager create-secret \
      --name "$TAILSCALE_SECRET_NAME" \
      --secret-string "$auth_key" \
      --profile "$AWS_PROFILE" \
      --region "$AWS_REGION" >/dev/null
    echo "created Tailscale auth key secret: $TAILSCALE_SECRET_NAME"
    return 0
  fi

  cat >&2 <<MSG
Missing AWS Secrets Manager secret: $TAILSCALE_SECRET_NAME

Create it with one of:
  TAILSCALE_AUTH_KEY='tskey-auth-REPLACE_ME' make preflight
  ./scripts/create-tailscale-secret.sh '$TAILSCALE_SECRET_NAME' 'tskey-auth-REPLACE_ME'

You can also place the key in ./tailscale-auth-key for local automation; it is gitignored.
MSG
  exit 3
}

ensure_tailscale_secret
mkdir -p out logs
printf 'preflight ok: profile=%s region=%s\n' "$AWS_PROFILE" "$AWS_REGION"
