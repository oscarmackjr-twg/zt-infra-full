#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TF_DIR="$ROOT_DIR/terraform"

missing=0

run_or_warn() {
  local tool="$1"
  shift
  if command -v "$tool" >/dev/null 2>&1; then
    echo "==> Running $tool $*"
    "$tool" "$@"
  else
    echo "WARN: $tool is not installed; skipping. Install it to enforce local policy checks." >&2
    missing=1
  fi
}

run_or_warn checkov -d "$TF_DIR" --config-file "$ROOT_DIR/.checkov.yml"
run_or_warn tfsec "$TF_DIR" --config-file "$ROOT_DIR/.tfsec.yml"

if [[ "$missing" -eq 1 ]]; then
  cat >&2 <<'MSG'

Policy scan completed with missing local tools.
Recommended local install options:
  python3 -m pip install checkov
  brew install tfsec

GitHub Actions will still run policy checks in CI.
MSG
fi
