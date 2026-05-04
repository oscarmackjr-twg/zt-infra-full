#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_NAME="${project_name}"
AWS_REGION="${aws_region}"
TAILSCALE_SECRET_NAME="${tailscale_secret_name}"
# Non-secret deployment marker. Changing the Secrets Manager version ID changes
# EC2 user data and forces bootstrap to rerun without embedding the auth key.
TAILSCALE_SECRET_VERSION_ID="${tailscale_secret_version_id}"
AUDIT_KMS_KEY_ID="${audit_kms_key_id}"
AUDIT_LOG_GROUP_NAME="${audit_log_group_name}"
BOOTSTRAP_LOG="/var/log/zt-bootstrap.log"
VERIFY_JSON="/var/log/zt-verify.json"
STATE_JSON="/var/log/zt-bootstrap-state.json"
CURRENT_STEP="init"
FAILED_STEP=""
SELF_HEALING_ATTEMPTS="[]"
CLEANUP_PATHS=()

mkdir -p /var/log
exec > >(tee -a "$BOOTSTRAP_LOG") 2>&1

step() {
  CURRENT_STEP="$1 $2"
  echo
  echo "--- [$1] $2 ---"
  date -Is
}

cleanup_paths() {
  local path
  if ! declare -p CLEANUP_PATHS >/dev/null 2>&1; then
    return 0
  fi
  for path in "$${CLEANUP_PATHS[@]:-}"; do
    if [[ -n "$path" && "$path" == /tmp/* ]]; then
      rm -rf "$path" || true
    fi
  done
}

require_command() {
  local command_name="$1"
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "Required command is missing: $command_name"
    exit 20
  fi
}

record_heal() {
  local action="$1"
  local status="$2"
  SELF_HEALING_ATTEMPTS="$(jq -cn --argjson old "$SELF_HEALING_ATTEMPTS" --arg action "$action" --arg status "$status" --arg ts "$(date -Is)" '$old + [{action:$action,status:$status,ts:$ts}]')"
}

write_state() {
  local status="$1"
  jq -n \
    --arg project "$PROJECT_NAME" \
    --arg status "$status" \
    --arg current_step "$CURRENT_STEP" \
    --arg failed_step "$FAILED_STEP" \
    --argjson self_healing_attempts "$SELF_HEALING_ATTEMPTS" \
    --arg updated_at "$(date -Is)" \
    '{project:$project,status:$status,current_step:$current_step,failed_step:$failed_step,self_healing_attempts:$self_healing_attempts,updated_at:$updated_at}' \
    > "$STATE_JSON"
}

write_verify_json() {
  local status="$1"
  local ts_json='{}'
  local dns_name=''
  local online='false'
  local ts_version='not-installed'
  local nginx_status='unknown'
  local provisioner_status='unknown'
  local serve_working='none'
  local serve_errors='[]'
  local serve_status='{}'
  local test_url=''

  if command -v tailscale >/dev/null 2>&1; then
    ts_version="$(tailscale version 2>/dev/null | head -n 1 || echo unknown)"
    ts_json="$(tailscale status --json 2>/dev/null || echo '{}')"
    dns_name="$(echo "$ts_json" | jq -r '.Self.DNSName // empty' 2>/dev/null || true)"
    online="$(echo "$ts_json" | jq -r '.Self.Online // false' 2>/dev/null || echo false)"
  fi

  if command -v systemctl >/dev/null 2>&1; then
    nginx_status="$(systemctl is-active nginx 2>/dev/null || true)"
    provisioner_status="$(systemctl is-active zt-provisioner 2>/dev/null || true)"
  fi

  if [[ -f /tmp/zt-serve-result.json ]]; then
    serve_working="$(jq -r '.working // "none"' /tmp/zt-serve-result.json 2>/dev/null || echo none)"
    serve_errors="$(jq -c '.errors // []' /tmp/zt-serve-result.json 2>/dev/null || echo '[]')"
    serve_status="$(jq -c '.status // {}' /tmp/zt-serve-result.json 2>/dev/null || echo '{}')"
  fi
  if [[ -n "$dns_name" ]]; then
    test_url="https://$${dns_name%.}"
  fi

  jq -n \
    --arg project "$PROJECT_NAME" \
    --arg bootstrap_status "$status" \
    --arg current_step "$CURRENT_STEP" \
    --arg failed_step "$FAILED_STEP" \
    --argjson self_healing_attempts "$SELF_HEALING_ATTEMPTS" \
    --arg ts_version "$ts_version" \
    --arg hostname "$(hostname)" \
    --arg dns_name "$dns_name" \
    --argjson online "$online" \
    --arg serve_working "$serve_working" \
    --argjson serve_errors "$serve_errors" \
    --argjson serve_status "$serve_status" \
    --arg nginx "$nginx_status" \
    --arg provisioner "$provisioner_status" \
    --arg test_url "$test_url" \
    --arg verified_at "$(date -Is)" \
    '{project:$project,bootstrap:{status:$bootstrap_status,current_step:$current_step,failed_step:$failed_step,self_healing_attempts:$self_healing_attempts},tailscale:{version:$ts_version,hostname:$hostname,dnsName:$dns_name,online:$online},serve_syntax:{working:$serve_working,errors:$serve_errors,status:$serve_status},services:{nginx:$nginx,zt_provisioner:$provisioner},test_url:$test_url,verified_at:$verified_at}' \
    > "$VERIFY_JSON"
  cat "$VERIFY_JSON"
}

on_error() {
  local exit_code=$?
  FAILED_STEP="$CURRENT_STEP"
  echo "ERROR: bootstrap failed at step '$FAILED_STEP' with exit code $exit_code"
  write_state "failed"
  write_verify_json "failed" || true
  exit "$exit_code"
}
trap on_error ERR
trap cleanup_paths EXIT

retry() {
  local attempts="$1"
  local delay="$2"
  local label="$3"
  shift 3
  local n=1
  until "$@"; do
    local rc=$?
    if (( n >= attempts )); then
      record_heal "$label" "failed_after_$${attempts}_attempts"
      return "$rc"
    fi
    record_heal "$label" "retry_$${n}"
    echo "WARN: $label failed with $rc; retrying in $${delay}s ($n/$attempts)"
    sleep "$delay"
    n=$((n + 1))
  done
  record_heal "$label" "ok"
}

heal_dpkg() {
  local n=1
  while fuser /var/lib/dpkg/lock-frontend >/dev/null 2>&1 || fuser /var/lib/apt/lists/lock >/dev/null 2>&1; do
    if (( n > 12 )); then
      record_heal "apt-lock-wait" "timeout"
      return 1
    fi
    record_heal "apt-lock-wait" "waiting_$${n}"
    sleep 10
    n=$((n + 1))
  done
  retry 3 5 "dpkg-configure" dpkg --configure -a
}

apt_install() {
  heal_dpkg
  retry 5 15 "apt-update" bash -c 'apt-get update -y'
  heal_dpkg
  retry 5 15 "apt-install-base-packages" apt-get install -y "$@"
}

wait_for_file() {
  local path="$1"
  local attempts="$2"
  local delay="$3"
  local label="$4"
  local n=1
  until [[ -f "$path" ]]; do
    if (( n >= attempts )); then
      record_heal "$label" "timeout"
      return 1
    fi
    record_heal "$label" "wait_$${n}"
    sleep "$delay"
    n=$((n + 1))
  done
  record_heal "$label" "ok"
}

wait_for_service_active() {
  local service="$1"
  local attempts="$2"
  local delay="$3"
  local n=1
  until systemctl is-active --quiet "$service"; do
    if (( n >= attempts )); then
      record_heal "wait-service-$service" "timeout"
      return 1
    fi
    record_heal "wait-service-$service" "wait_$${n}"
    sleep "$delay"
    n=$((n + 1))
  done
  record_heal "wait-service-$service" "ok"
}

ensure_aws_cli() {
  if command -v aws >/dev/null 2>&1; then
    record_heal "install-aws-cli" "already-installed"
    return 0
  fi

  local tmpdir
  tmpdir="$(mktemp -d)"
  CLEANUP_PATHS+=("$tmpdir")
  retry 5 10 "download-aws-cli" curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "$tmpdir/awscliv2.zip"
  wait_for_file "$tmpdir/awscliv2.zip" 3 1 "aws-cli-zip-present"
  unzip -q "$tmpdir/awscliv2.zip" -d "$tmpdir"
  "$tmpdir/aws/install" --update
  rm -rf "$tmpdir"
  command -v aws >/dev/null 2>&1
  record_heal "install-aws-cli" "ok"
}

ensure_ssm_agent() {
  if systemctl list-unit-files amazon-ssm-agent.service >/dev/null 2>&1; then
    record_heal "install-ssm-agent" "already-installed"
    ensure_service_active amazon-ssm-agent
    return 0
  fi

  if command -v snap >/dev/null 2>&1; then
    retry 5 10 "snap-install-ssm-agent" snap install amazon-ssm-agent --classic
    systemctl enable --now snap.amazon-ssm-agent.amazon-ssm-agent.service || true
    if wait_for_service_active snap.amazon-ssm-agent.amazon-ssm-agent.service 6 2; then
      record_heal "install-ssm-agent" "ok-snap"
      return 0
    fi
  fi

  local deb_path="/tmp/amazon-ssm-agent.deb"
  retry 5 10 "download-ssm-agent" curl -fsSL "https://s3.$AWS_REGION.amazonaws.com/amazon-ssm-$AWS_REGION/latest/debian_amd64/amazon-ssm-agent.deb" -o "$deb_path"
  wait_for_file "$deb_path" 3 1 "ssm-agent-deb-present"
  dpkg -i "$deb_path" || apt-get install -f -y
  ensure_service_active amazon-ssm-agent
  record_heal "install-ssm-agent" "ok-deb"
}

ensure_nodejs_runtime() {
  local major="0"
  if command -v node >/dev/null 2>&1; then
    major="$(node --version | sed -E 's/^v([0-9]+).*/\1/')"
  fi
  if (( major >= 20 )) && command -v npm >/dev/null 2>&1; then
    record_heal "install-nodejs-runtime" "already-installed"
    return 0
  fi

  install -d -m 0755 /usr/share/keyrings
  retry 5 10 "download-nodesource-key" curl -fsSL "https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key" -o /tmp/nodesource-repo.gpg.key
  gpg --dearmor -o /usr/share/keyrings/nodesource.gpg /tmp/nodesource-repo.gpg.key
  chmod 0644 /usr/share/keyrings/nodesource.gpg
  echo "deb [signed-by=/usr/share/keyrings/nodesource.gpg] https://deb.nodesource.com/node_22.x nodistro main" > /etc/apt/sources.list.d/nodesource.list
  chmod 0644 /etc/apt/sources.list.d/nodesource.list
  retry 5 10 "apt-update-nodesource" apt-get update -y
  retry 5 10 "apt-install-nodejs-runtime" apt-get install -y nodejs

  major="$(node --version | sed -E 's/^v([0-9]+).*/\1/')"
  if (( major < 20 )); then
    echo "Node.js >=20 is required for CDP SDK; found $(node --version)"
    return 1
  fi
  command -v npm >/dev/null 2>&1
  record_heal "install-nodejs-runtime" "ok"
}

ensure_service_active() {
  local service="$1"
  systemctl daemon-reload || true
  systemctl enable "$service" || true
  if ! systemctl is-active --quiet "$service"; then
    record_heal "restart-$service" "attempt"
    systemctl restart "$service" || true
  fi
  wait_for_service_active "$service" 6 2
}

tailscale_up_once() {
  local err_file="/tmp/tailscale-up.err"
  rm -f "$err_file"
  if tailscale up --auth-key "$TAILSCALE_AUTH_KEY" --hostname "$PROJECT_NAME-$(hostname)" --ssh --accept-dns=true 2>"$err_file"; then
    rm -f "$err_file"
    return 0
  fi

  local err_text
  err_text="$(tail -n 20 "$err_file" 2>/dev/null | tr '\n' ' ')"
  if echo "$err_text" | grep -Eiq 'invalid key|not valid|key.*expired|auth.*key.*(invalid|expired|reusable)'; then
    record_heal "tailscale-auth-key" "invalid"
    echo "ERROR: Tailscale auth key was rejected. Rotate AWS Secrets Manager secret '$TAILSCALE_SECRET_NAME'."
    rm -f "$err_file"
    return 90
  fi

  echo "$err_text"
  rm -f "$err_file"
  return 1
}

join_tailscale() {
  if tailscale status --json 2>/dev/null | jq -e '.Self.Online == true' >/dev/null 2>&1; then
    record_heal "tailscale-up" "already-online"
    return 0
  fi

  local attempts=3
  local delay=10
  local n=1
  local rc=0
  until tailscale_up_once; do
    rc=$?
    if (( rc == 90 )); then
      record_heal "tailscale-up" "non_retryable_auth_key"
      return "$rc"
    fi
    if (( n >= attempts )); then
      record_heal "tailscale-up" "failed_after_$${attempts}_attempts"
      return "$rc"
    fi
    record_heal "tailscale-up" "retry_$${n}"
    echo "WARN: tailscale-up failed with $rc; retrying in $${delay}s ($n/$attempts)"
    sleep "$delay"
    n=$((n + 1))
  done
  record_heal "tailscale-up" "ok"
}

export DEBIAN_FRONTEND=noninteractive
write_state "running"

step "1/10" "bootstrap start"
date -Is

step "2/10" "install base packages"
apt_install ca-certificates curl gnupg unzip jq nginx
require_command jq
ensure_nodejs_runtime
ensure_aws_cli
ensure_ssm_agent
ensure_service_active nginx

step "3/10" "install tailscale"
if ! command -v tailscale >/dev/null 2>&1; then
  retry 5 10 "install-tailscale" bash -o pipefail -c 'curl -fsSL https://tailscale.com/install.sh | sh'
else
  record_heal "install-tailscale" "already-installed"
fi
ensure_service_active tailscaled

step "4/10" "install landing page"
cat > /var/www/html/index.html <<HTML
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>ZT Infra v2</title>
  <style>
    body { font-family: system-ui, -apple-system, Segoe UI, sans-serif; margin: 3rem; line-height: 1.45; }
    code { background: #eee; padding: 0.1rem 0.25rem; border-radius: 0.25rem; }
  </style>
</head>
<body>
  <h1>ZT Infra v2 MVP</h1>
  <p>Nginx landing page is alive on <code>$(hostname)</code>.</p>
  <p>Access is intended through Tailscale Serve, not public ingress.</p>
</body>
</html>
HTML
ensure_service_active nginx

step "5/10" "install zt-provisioner"
if ! id -u zt-provisioner >/dev/null 2>&1; then
  useradd --system --home-dir /var/lib/zt-provisioner --create-home --shell /usr/sbin/nologin zt-provisioner
fi
install -d -m 0755 -o root -g root /opt/zt-provisioner /opt/zt-provisioner/src /opt/zt-provisioner/policies /etc/zt-provisioner
install -d -m 0750 -o zt-provisioner -g zt-provisioner /var/lib/zt-provisioner
cat > /opt/zt-provisioner/package.json <<'JSON'
${provisioner_package_json}
JSON
cat > /opt/zt-provisioner/policies/actions.json <<'JSON'
${provisioner_actions_json}
JSON
install -m 0644 -o root -g root /opt/zt-provisioner/policies/actions.json /etc/zt-provisioner/actions-policy.json
cat > /opt/zt-provisioner/src/policy.js <<'JS'
${provisioner_policy_js}
JS
cat > /opt/zt-provisioner/src/audit.js <<'JS'
${provisioner_audit_js}
JS
cat > /opt/zt-provisioner/src/daal.js <<'JS'
${provisioner_daal_js}
JS
cat > /opt/zt-provisioner/src/server.js <<'JS'
${provisioner_server_js}
JS
cat > /etc/zt-provisioner/daal.env <<'ENV'
DAAL_ENABLED=${daal_enabled}
DAAL_PROVIDER_MODE=${daal_provider_mode}
DAAL_NETWORK=${daal_network}
DAAL_CONTRACT_ADDRESS=${daal_contract_address}
DAAL_BATCH_SIZE=${daal_batch_size}
CDP_EVM_ACCOUNT_ADDRESS=${cdp_evm_account_address}
ENV
if [[ "${daal_enabled}" == "true" ]]; then
  daal_secret_json="$(retry 5 10 "fetch-daal-secret" aws secretsmanager get-secret-value --region "$AWS_REGION" --secret-id "${daal_secret_name}" --query SecretString --output text)"
  if [[ -z "$daal_secret_json" || "$daal_secret_json" == "None" ]]; then
    echo "DAAL runtime secret '${daal_secret_name}' was empty"
    exit 12
  fi
  printf '%s' "$daal_secret_json" | jq -r '
    def envline($k): select(has($k)) | "\($k)=\(.[$k])";
    envline("CDP_API_KEY_ID"),
    envline("CDP_API_KEY_SECRET"),
    envline("CDP_WALLET_SECRET"),
    envline("ALCHEMY_API_KEY"),
    envline("THIRDWEB_SECRET_KEY")
  ' >> /etc/zt-provisioner/daal.env
fi
chown root:root /etc/zt-provisioner/daal.env
chmod 0640 /etc/zt-provisioner/daal.env
retry 5 10 "npm-install-provisioner" bash -c 'cd /opt/zt-provisioner && npm install --omit=dev'
chown -R root:root /opt/zt-provisioner /etc/zt-provisioner
chmod 0755 /opt/zt-provisioner /opt/zt-provisioner/src /opt/zt-provisioner/policies
chmod 0644 /opt/zt-provisioner/package.json /opt/zt-provisioner/src/*.js /opt/zt-provisioner/policies/actions.json /etc/zt-provisioner/actions-policy.json
cat > /etc/systemd/system/zt-provisioner.service <<'UNIT'
[Unit]
Description=ZT Provisioner MVP
After=network-online.target
Wants=network-online.target

[Service]
WorkingDirectory=/opt/zt-provisioner
ExecStart=/usr/bin/node /opt/zt-provisioner/src/server.js
Restart=always
RestartSec=3
User=zt-provisioner
Group=zt-provisioner
Environment=NODE_ENV=production
Environment=AWS_REGION=${aws_region}
Environment=ACTION_POLICY_FILE=/etc/zt-provisioner/actions-policy.json
Environment=AUDIT_KMS_KEY_ID=${audit_kms_key_id}
Environment=AUDIT_LOG_GROUP_NAME=${audit_log_group_name}
Environment=AUDIT_STATE_FILE=/var/lib/zt-provisioner/audit-chain.jsonl
Environment=DAAL_SYSTEM_OF_RECORD_FILE=/var/lib/zt-provisioner/daal-attestations.jsonl
EnvironmentFile=/etc/zt-provisioner/daal.env
StateDirectory=zt-provisioner
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
CapabilityBoundingSet=
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
ReadWritePaths=/var/lib/zt-provisioner

[Install]
WantedBy=multi-user.target
UNIT
ensure_service_active zt-provisioner

step "6/10" "fetch tailscale auth key from AWS Secrets Manager"
TAILSCALE_AUTH_KEY="$(retry 5 10 "fetch-tailscale-secret" aws secretsmanager get-secret-value --region "$AWS_REGION" --secret-id "$TAILSCALE_SECRET_NAME" --query SecretString --output text)"
if [[ -z "$TAILSCALE_AUTH_KEY" || "$TAILSCALE_AUTH_KEY" == "None" ]]; then
  echo "Tailscale auth key secret was empty"
  exit 11
fi

step "7/10" "join tailscale"
join_tailscale
sleep 5

step "8/10" "tailscale serve syntax detector"
cat > /opt/detect-tailscale-serve.sh <<'SH'
#!/usr/bin/env bash
set -euo pipefail
WORKING="none"
ERRORS="[]"
STATUS_JSON="{}"
TS_VERSION="$(tailscale version 2>/dev/null | head -n 1 || echo unknown)"
HELP_HEAD="$(tailscale serve --help 2>&1 | head -n 20 | tr '\n' ' ' || true)"

record_error() {
  local label="$1"
  local file="$2"
  local message
  message="$(tail -n 8 "$file" 2>/dev/null | tr '\n' ' ')"
  ERRORS="$(jq -cn --argjson old "$ERRORS" --arg label "$label" --arg message "$message" '$old + [{label:$label,message:$message}]')"
}

serve_status_has_proxy() {
  STATUS_JSON="$(tailscale serve status --json 2>/dev/null || echo '{}')"
  echo "$STATUS_JSON" | jq -e '
    [
      (.Web // {} | to_entries[]? | .value.Handlers // {} | to_entries[]? | .value.Proxy // empty),
      (.TCP // {} | to_entries[]? | .value.Handlers // {} | to_entries[]? | .value.Proxy // empty)
    ]
    | any(. == "http://127.0.0.1:80" or . == "http://localhost:80")
  ' >/dev/null 2>&1
}

try_serve() {
  local label="$1"
  shift
  local out="/tmp/serve-$label.out"
  local err="/tmp/serve-$label.err"
  rm -f "$out" "$err"
  if "$@" >"$out" 2>"$err" && serve_status_has_proxy; then
    WORKING="$label"
    return 0
  fi
  record_error "$label" "$err"
  return 1
}

tailscale serve reset >/tmp/serve-reset.out 2>/tmp/serve-reset.err || true

try_serve "current-set-path" tailscale serve --bg --yes --https=443 --set-path=/ http://127.0.0.1:80 ||
try_serve "current" tailscale serve --bg --https=443 http://127.0.0.1:80 ||
try_serve "current-partial-target" tailscale serve --bg --https=443 127.0.0.1:80 ||
try_serve "legacy-1.52" tailscale serve --bg https / http://127.0.0.1:80 ||
true

jq -n \
  --arg working "$WORKING" \
  --arg version "$TS_VERSION" \
  --arg help_head "$HELP_HEAD" \
  --argjson errors "$ERRORS" \
  --argjson status "$STATUS_JSON" \
  '{working:$working,version:$version,help_head:$help_head,errors:$errors,status:$status}' \
  > /tmp/zt-serve-result.json
cat /tmp/zt-serve-result.json
[[ "$WORKING" != "none" ]]
SH
chmod +x /opt/detect-tailscale-serve.sh
if ! /opt/detect-tailscale-serve.sh; then
  record_heal "tailscale-serve-detect" "failed"
  exit 12
else
  record_heal "tailscale-serve-detect" "ok"
fi

step "9/10" "local service verification"
curl -fsS http://127.0.0.1/ >/dev/null
curl -fsS http://127.0.0.1:3000/health | jq -e '.ok == true' >/dev/null
ensure_service_active nginx
ensure_service_active zt-provisioner

step "10/10" "write verification log"
write_state "ok"
write_verify_json "ok"

echo "bootstrap complete"
date -Is
