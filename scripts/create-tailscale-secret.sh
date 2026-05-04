#!/usr/bin/env bash
set -euo pipefail
: "${AWS_PROFILE:?Set AWS_PROFILE to your AWS CLI profile}"
: "${AWS_REGION:=us-east-2}"
if [[ $# -eq 1 && -n "${TAILSCALE_SECRET_NAME:-}" ]]; then
  SECRET_NAME="$TAILSCALE_SECRET_NAME"
  AUTH_KEY="$1"
elif [[ $# -eq 2 ]]; then
  SECRET_NAME="$1"
  AUTH_KEY="$2"
else
  echo "Usage: $0 [secret-name] <tailscale-auth-key>"
  echo "Or set TAILSCALE_SECRET_NAME and run: $0 <tailscale-auth-key>"
  exit 2
fi
if [[ ! "$SECRET_NAME" =~ ^[A-Za-z0-9/_+=.@-]+$ ]]; then
  echo "Secret name must contain only AWS Secrets Manager-safe path characters." >&2
  exit 2
fi
if [[ ! "$AUTH_KEY" =~ ^tskey-auth-[A-Za-z0-9]+-[A-Za-z0-9]+$ ]]; then
  echo "Tailscale auth key format is invalid; expected tskey-auth-... without surrounding whitespace." >&2
  exit 2
fi
if aws secretsmanager describe-secret --secret-id "$SECRET_NAME" --profile "$AWS_PROFILE" --region "$AWS_REGION" >/dev/null 2>&1; then
  aws secretsmanager put-secret-value --secret-id "$SECRET_NAME" --secret-string "$AUTH_KEY" --profile "$AWS_PROFILE" --region "$AWS_REGION" >/dev/null
  echo "updated secret: $SECRET_NAME"
else
  aws secretsmanager create-secret --name "$SECRET_NAME" --secret-string "$AUTH_KEY" --profile "$AWS_PROFILE" --region "$AWS_REGION" >/dev/null
  echo "created secret: $SECRET_NAME"
fi
