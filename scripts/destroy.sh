#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/terraform"

: "${CONFIRM_DESTROY:=}"
if [[ "$CONFIRM_DESTROY" != "zt-infra-v2" ]]; then
  cat >&2 <<'MSG'
Refusing to destroy without explicit confirmation.

Run:
  CONFIRM_DESTROY=zt-infra-v2 make destroy
MSG
  exit 2
fi

terraform destroy -auto-approve
