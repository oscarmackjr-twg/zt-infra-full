#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

failures=0

fail() {
  echo "FAIL: $*" >&2
  failures=1
}

warn() {
  echo "WARN: $*" >&2
}

check_source_for_secrets() {
  local secret_hits
  secret_hits="$(rg -n \
    -g '!terraform/*.tfstate*' \
    -g '!terraform/.terraform/**' \
    -g '!out/**' \
    -g '!logs/**' \
    -g '!.venv/**' \
    -g '!**/__pycache__/**' \
    -g '!node_modules/**' \
    'tskey-auth-[A-Za-z0-9]+-[A-Za-z0-9]{8,}|BEGIN [A-Z ]*PRIVATE KEY|aws_secret_access_key[[:space:]]*=' \
    . || true)"

  if [[ -n "$secret_hits" ]]; then
    echo "$secret_hits" >&2
    fail "publishable source appears to contain secrets"
  fi
}

check_source_for_public_disclosures() {
  local disclosure_hits
  disclosure_hits="$(rg -n \
    -g '!node_modules/**' \
    -g '!public_repo_seed/**' \
    -g '!tests/test_static_repo.py' \
    -g '!scripts/github-ready.sh' \
    -g '!terraform/.terraform/**' \
    -g '!out/**' \
    -g '!logs/**' \
    -g '!evidence/**' \
    -g '!.venv/**' \
    'AWSAdministratorAccess-[0-9]{12}|arn:aws:[^[:space:]]+:[0-9]{12}:|/[Uu]sers/[A-Za-z0-9._-]+' \
    . || true)"

  if [[ -n "$disclosure_hits" ]]; then
    echo "$disclosure_hits" >&2
    fail "publishable source contains public disclosure data that must be redacted"
  fi
}

check_tracked_forbidden_files() {
  if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    warn "not a git repository yet; skipping tracked-file checks"
    return 0
  fi

  local tracked_forbidden
  tracked_forbidden="$(git ls-files | rg '(^|/)(terraform\.tfstate(\.backup)?|\.terraform/|logs/|out/|\.venv/|__pycache__/)|\.(pem|key|zip|pyc)$' || true)"
  if [[ -n "$tracked_forbidden" ]]; then
    echo "$tracked_forbidden" >&2
    fail "generated, state, cache, or secret files are tracked"
  fi
}

check_local_generated_artifacts() {
  local generated
  generated="$(find . -maxdepth 3 -type f \( \
    -path './terraform/terraform.tfstate' -o \
    -path './terraform/terraform.tfstate.backup' -o \
    -path './logs/*' -o \
    -path './out/*' -o \
    -path './tests/__pycache__/*' -o \
    -path './.pytest_cache/*' \
    \) -print)"

  if [[ -n "$generated" ]]; then
    warn "local generated artifacts exist and must stay untracked:"
    echo "$generated" >&2
  fi
}

check_required_files() {
  local required=(
    ".gitignore"
    ".github/workflows/ci.yml"
    ".github/dependabot.yml"
    ".github/PULL_REQUEST_TEMPLATE.md"
    "LICENSE"
    "SECURITY.md"
    "CONTRIBUTING.md"
    "CODE_OF_CONDUCT.md"
    "README.md"
    "Makefile"
    "terraform/main.tf"
    "terraform/.terraform.lock.hcl"
    "terraform/user-data.sh.tpl"
    "tests/test_static_repo.py"
    "tests/test_bootstrap_simulation.py"
  )

  local path
  for path in "${required[@]}"; do
    if [[ ! -e "$path" ]]; then
      fail "missing required publish file: $path"
    fi
  done
}

check_required_files
check_source_for_secrets
check_source_for_public_disclosures
check_tracked_forbidden_files
check_local_generated_artifacts

if [[ "$failures" -ne 0 ]]; then
  echo "github-ready failed" >&2
  exit 1
fi

echo "github-ready ok"
