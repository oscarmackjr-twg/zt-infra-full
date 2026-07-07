import json
import os
import subprocess
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def bootstrap_prelude(tmp_path):
    tpl = (ROOT / "terraform/user-data.sh.tpl").read_text()
    prelude = tpl.split("export DEBIAN_FRONTEND=noninteractive", 1)[0]
    prelude = prelude.replace("${project_name}", "zt-infra-v2")
    prelude = prelude.replace("${aws_region}", "us-east-2")
    prelude = prelude.replace("${tailscale_secret_name}", "zt-infra/tailscale-auth-key")
    prelude = prelude.replace("${tailscale_secret_version_id}", "test-secret-version")
    prelude = prelude.replace("${audit_kms_key_id}", "arn:aws:kms:us-east-2:<AWS_ACCOUNT_ID>:key/test")
    prelude = prelude.replace("${audit_log_group_name}", "/aws/zt/zt-infra-v2/agent-audit")
    prelude = prelude.replace("$${", "${")
    prelude = prelude.replace('BOOTSTRAP_LOG="/var/log/zt-bootstrap.log"', f'BOOTSTRAP_LOG="{tmp_path}/zt-bootstrap.log"')
    prelude = prelude.replace('VERIFY_JSON="/var/log/zt-verify.json"', f'VERIFY_JSON="{tmp_path}/zt-verify.json"')
    prelude = prelude.replace('STATE_JSON="/var/log/zt-bootstrap-state.json"', f'STATE_JSON="{tmp_path}/zt-bootstrap-state.json"')
    prelude = prelude.replace('mkdir -p /var/log', f'mkdir -p "{tmp_path}"')
    prelude = prelude.replace('exec > >(tee -a "$BOOTSTRAP_LOG") 2>&1', ':')
    script = tmp_path / "bootstrap-prelude.sh"
    script.write_text(prelude)
    return script


def run_bash(script):
    bash = os.environ.get("BASH_EXE", "bash")
    return subprocess.run([bash, str(script)], text=True, capture_output=True, check=False)


def tailscale_serve_detector(tmp_path):
    tpl = (ROOT / "terraform/user-data.sh.tpl").read_text()
    start = tpl.index("cat > /opt/detect-tailscale-serve.sh <<'SH'") + len(
        "cat > /opt/detect-tailscale-serve.sh <<'SH'"
    )
    end = tpl.index("\nSH\nchmod +x /opt/detect-tailscale-serve.sh", start)
    script = tmp_path / "detect-tailscale-serve.sh"
    script.write_text(tpl[start:end].lstrip())
    script.chmod(0o755)
    return script


def test_retry_records_retries_and_failure(tmp_path):
    prelude = bootstrap_prelude(tmp_path)
    scenario = tmp_path / "retry-failure.sh"
    scenario.write_text(
        textwrap.dedent(
            f"""
            source "{prelude}"
            retry 3 0 simulated-failure bash -c 'exit 42' || rc=$?
            echo "$SELF_HEALING_ATTEMPTS"
            exit "$rc"
            """
        )
    )

    result = run_bash(scenario)

    assert result.returncode == 42
    assert "failed_after_3_attempts" in result.stderr + result.stdout


def test_error_trap_writes_failed_state_and_verify_json(tmp_path):
    prelude = bootstrap_prelude(tmp_path)
    scenario = tmp_path / "trap-failure.sh"
    scenario.write_text(
        textwrap.dedent(
            f"""
            source "{prelude}"
            step "sim" "forced failure"
            false
            """
        )
    )

    result = run_bash(scenario)

    assert result.returncode == 1
    state = json.loads((tmp_path / "zt-bootstrap-state.json").read_text())
    verify = json.loads((tmp_path / "zt-verify.json").read_text())
    assert state["status"] == "failed"
    assert state["failed_step"] == "sim forced failure"
    assert verify["bootstrap"]["status"] == "failed"
    assert verify["bootstrap"]["failed_step"] == "sim forced failure"


def test_wait_for_file_times_out_with_observable_heal_record(tmp_path):
    prelude = bootstrap_prelude(tmp_path)
    scenario = tmp_path / "wait-file-failure.sh"
    scenario.write_text(
        textwrap.dedent(
            f"""
            source "{prelude}"
            wait_for_file "{tmp_path}/missing" 2 0 simulated-file || rc=$?
            echo "$SELF_HEALING_ATTEMPTS"
            exit "$rc"
            """
        )
    )

    result = run_bash(scenario)

    assert result.returncode != 0
    assert "simulated-file" in result.stdout + result.stderr
    assert "timeout" in result.stdout + result.stderr


def test_join_tailscale_rejected_auth_key_is_non_retryable(tmp_path):
    prelude = bootstrap_prelude(tmp_path)
    scenario = tmp_path / "tailscale-invalid-key.sh"
    scenario.write_text(
        textwrap.dedent(
            f"""
            source "{prelude}"
            TAILSCALE_AUTH_KEY="redacted"
            tailscale() {{
              if [[ "$1" == "status" ]]; then
                return 1
              fi
              if [[ "$1" == "up" ]]; then
                echo "backend error: invalid key: API key redacted not valid" >&2
                return 1
              fi
              return 0
            }}
            join_tailscale || rc=$?
            echo "$SELF_HEALING_ATTEMPTS"
            exit "$rc"
            """
        )
    )

    result = run_bash(scenario)

    assert result.returncode == 90
    output = result.stdout + result.stderr
    assert "tailscale-auth-key" in output
    assert "invalid" in output
    assert "non_retryable_auth_key" in output


def test_tailscale_serve_detector_accepts_current_syntax(tmp_path):
    detector = tailscale_serve_detector(tmp_path)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    marker = tmp_path / "served"
    fake_tailscale = fake_bin / "tailscale"
    fake_tailscale.write_text(
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            set -euo pipefail
            if [[ "$1" == "version" ]]; then
              echo "1.96.4"
              exit 0
            fi
            if [[ "$1" == "serve" && "${{2:-}}" == "--help" ]]; then
              echo "serve help"
              exit 0
            fi
            if [[ "$1" == "serve" && "${{2:-}}" == "reset" ]]; then
              rm -f "{marker}"
              exit 0
            fi
            if [[ "$1" == "serve" && "${{2:-}}" == "status" ]]; then
              if [[ -f "{marker}" ]]; then
                printf '%s\\n' '{{"Web":{{"host":{{"Handlers":{{"/":{{"Proxy":"http://127.0.0.1:80"}}}}}}}}}}'
              else
                printf '%s\\n' '{{}}'
              fi
              exit 0
            fi
            if [[ "$*" == "serve --bg --yes --https=443 --set-path=/ http://127.0.0.1:80" ]]; then
              touch "{marker}"
              exit 0
            fi
            echo "unsupported current test args: $*" >&2
            exit 2
            """
        )
    )
    fake_tailscale.chmod(0o755)
    scenario = tmp_path / "serve-current.sh"
    scenario.write_text(
        textwrap.dedent(
            f"""
            export PATH="{fake_bin}:$PATH"
            cd "{tmp_path}"
            "{detector}"
            jq -e '.working == "current-set-path"' /tmp/zt-serve-result.json
            """
        )
    )

    result = run_bash(scenario)

    assert result.returncode == 0, result.stdout + result.stderr


def test_tailscale_serve_detector_falls_back_to_legacy_syntax(tmp_path):
    detector = tailscale_serve_detector(tmp_path)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    marker = tmp_path / "served"
    fake_tailscale = fake_bin / "tailscale"
    fake_tailscale.write_text(
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            set -euo pipefail
            if [[ "$1" == "version" ]]; then
              echo "1.50.0"
              exit 0
            fi
            if [[ "$1" == "serve" && "${{2:-}}" == "--help" ]]; then
              echo "legacy serve help"
              exit 0
            fi
            if [[ "$1" == "serve" && "${{2:-}}" == "reset" ]]; then
              rm -f "{marker}"
              exit 0
            fi
            if [[ "$1" == "serve" && "${{2:-}}" == "status" ]]; then
              if [[ -f "{marker}" ]]; then
                printf '%s\\n' '{{"Web":{{"host":{{"Handlers":{{"/":{{"Proxy":"http://127.0.0.1:80"}}}}}}}}}}'
              else
                printf '%s\\n' '{{}}'
              fi
              exit 0
            fi
            if [[ "$*" == "serve --bg https / http://127.0.0.1:80" ]]; then
              touch "{marker}"
              exit 0
            fi
            echo "unsupported until legacy fallback: $*" >&2
            exit 2
            """
        )
    )
    fake_tailscale.chmod(0o755)
    scenario = tmp_path / "serve-legacy.sh"
    scenario.write_text(
        textwrap.dedent(
            f"""
            export PATH="{fake_bin}:$PATH"
            cd "{tmp_path}"
            "{detector}"
            jq -e '.working == "legacy-1.52"' /tmp/zt-serve-result.json
            jq -e '.errors | length >= 1' /tmp/zt-serve-result.json
            """
        )
    )

    result = run_bash(scenario)

    assert result.returncode == 0, result.stdout + result.stderr
