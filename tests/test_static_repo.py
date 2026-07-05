from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def test_required_files_exist():
    required = [
        "terraform/main.tf",
        "terraform/user-data.sh.tpl",
        "provisioner/src/server.js",
        "scripts/preflight.sh",
        "scripts/deploy.sh",
        "scripts/policy-scan.sh",
        "scripts/windows/ZtCommon.ps1",
        "scripts/windows/Test-ZtPreflight.ps1",
        "scripts/windows/New-ZtTailscaleSecret.ps1",
        "scripts/windows/Invoke-ZtStatic.ps1",
        "scripts/windows/Invoke-ZtPolicy.ps1",
        "scripts/windows/Invoke-ZtDeploy.ps1",
        "scripts/windows/Invoke-ZtLive.ps1",
        "scripts/windows/Get-ZtLogs.ps1",
        "scripts/windows/Remove-ZtDeployment.ps1",
        "docs/windows-poc/AWS_POWERSHELL_POC.md",
        "zt_langgraph/client.py",
        "zt_langgraph/nodes.py",
        "zt_openai/assistants.py",
        "zt_openai/responses.py",
        "zt_openai/agents_sdk.py",
        "zt_mcp/gateway.py",
        "zt_a2a/proxy.py",
        "contracts/DAALog.sol",
        "daal/schema.sql",
        "provisioner/src/daal.js",
        "scripts/deploy-daal-thirdweb.sh",
        "docs/LANGGRAPH_PLUGIN.md",
        "docs/DAAL.md",
        "docs/A2A_POLICY_PROXY.md",
        "docs/INTEROPERABILITY_DEMO.md",
        "docs/OPENAI_AGENTS_SDK_GUARDRAIL_PLUGIN.md",
        "docs/OPENAI_ASSISTANTS_ZERO_TRUST_WRAPPER.md",
        "docs/OPENAI_RESPONSES_ZERO_TRUST_WRAPPER.md",
        "docs/MCP_ZERO_TRUST_GATEWAY.md",
        ".checkov.yml",
        ".tfsec.yml",
        ".github/workflows/ci.yml",
        "README.md",
        "AGENTS.md",
        "docs/presentations/agent_interoperability_demo_slide.md",
        "docs/presentations/agent_interoperability_appendix.md",
    ]
    missing = [p for p in required if not (ROOT / p).exists()]
    assert not missing


def test_daal_attestation_layer_is_wired():
    contract = (ROOT / "contracts/DAALog.sol").read_text()
    daal = (ROOT / "provisioner/src/daal.js").read_text()
    audit = (ROOT / "provisioner/src/audit.js").read_text()
    schema = (ROOT / "daal/schema.sql").read_text()
    docs = (ROOT / "docs/DAAL.md").read_text()
    package_json = (ROOT / "provisioner/package.json").read_text()
    deploy_script = (ROOT / "scripts/deploy-daal-thirdweb.sh").read_text()
    check_script = (ROOT / "scripts/check-das-config.mjs").read_text()
    env_example = (ROOT / ".env.example").read_text()

    for token in [
        "struct AuditRecord",
        "string agentId",
        "bytes32 actionHash",
        "uint256 timestamp",
        "string metadata",
        "event ActionLogged",
        "function logAction",
        "function logBatch",
    ]:
        assert token in contract
    assert "function delete" not in contract.lower()
    for token in [
        "NonceManager",
        "alchemyRpcUrl",
        "AlchemyReceiptVerifier",
        "CDPDAALContract",
        "ThirdwebEngineDAALContract",
        "THIRDWEB_ENGINE_URL",
        "validateDASConfig",
        "dasRuntimePlan",
        "cdp.evm.sendTransaction",
        "logAction(agentId",
        "enqueueAction",
        "attestAction",
        "drain",
        "merkleRootHex",
        "batchSize",
        "FileAttestationStore",
        "createDAALoggerFromEnv",
    ]:
        assert token in daal
    assert "attestAction" in audit
    assert "daal_attestations" in schema
    assert "agent_logs" in schema
    assert "blockchain_tx_hash" in schema
    assert "attestation_status" in schema
    for token in [
        "DAAL_ENABLED",
        "Alchemy",
        "thirdweb",
        "Coinbase Developer Platform",
        "CDP_EVM_ACCOUNT_ADDRESS",
        "THIRDWEB_ENGINE_URL",
        "ALCHEMY_API_KEY",
    ]:
        assert token in docs
        assert token in env_example
    assert "npx thirdweb deploy" in deploy_script
    assert '--path "${ROOT_DIR}/contracts"' in deploy_script
    assert "dasRuntimePlan" in check_script
    assert "ethers" in package_json
    assert "@coinbase/cdp-sdk" in package_json
    assert "viem" in package_json
    assert '"overrides"' in package_json
    assert '"axios": "1.15.2"' in package_json


def test_no_public_ingress_in_terraform():
    main_tf = (ROOT / "terraform/main.tf").read_text()
    assert re.search(r"resource\s+\"aws_default_security_group\"\s+\"locked_down\"", main_tf)
    assert "ingress = []" in main_tf
    assert 'cidr_ipv4         = "0.0.0.0/0"\n  ip_protocol       = "-1"' not in main_tf
    assert "AmazonSSMManagedInstanceCore" in main_tf
    assert "http_tokens                 = \"required\"" in main_tf
    assert "instance_metadata_tags      = \"disabled\"" in main_tf
    assert "encrypted   = true" in main_tf
    assert "revoke_rules_on_delete = true" in main_tf
    assert "aws_flow_log" in main_tf
    assert "retention_in_days = 365" in main_tf
    assert "aws_kms_key" in main_tf
    assert "enable_key_rotation     = true" in main_tf
    assert "kms_key_id        = aws_kms_key.vpc_flow_logs.arn" in main_tf


def test_terraform_security_guardrails_are_explicit():
    main_tf = (ROOT / "terraform/main.tf").read_text()
    variables_tf = (ROOT / "terraform/variables.tf").read_text()
    for token in [
        "aws_secretsmanager_secret_version",
        "tailscale_secret_version_id",
        "Tailscale direct WireGuard outbound",
        "AWS Time Sync Service",
        "aws_cloudwatch_log_group",
        "vpc-flow-logs.amazonaws.com",
        "traffic_type    = \"ALL\"",
        "aws_kms_alias",
        "aws_kms_key\" \"audit_signing",
        "aws_kms_key\" \"agent_audit_logs",
        "key_usage                = \"SIGN_VERIFY\"",
        "aws_cloudwatch_log_group\" \"agent_audit",
        "kms:Sign",
        "kms:EncryptionContext:aws:logs:arn",
        "precondition",
        "Refusing to deploy outside the configured allowed_aws_account_id",
        "Refusing to deploy outside us-east-2",
    ]:
        assert token in main_tf
    for token in [
        "allowed_aws_account_id",
        "aws_profile must be set explicitly",
        "var.aws_region == \"us-east-2\"",
        "approved small-instance allowlist",
        "AWS Secrets Manager-safe path characters",
    ]:
        assert token in variables_tf


def test_user_data_has_verify_log_and_fail_fast():
    tpl = (ROOT / "terraform/user-data.sh.tpl").read_text()
    assert "set -Eeuo pipefail" in tpl
    assert "/var/log/zt-bootstrap.log" in tpl
    assert "/var/log/zt-verify.json" in tpl
    assert "tailscale serve" in tpl
    assert "current-set-path" in tpl
    assert "legacy-1.52" in tpl
    assert "serve_status_has_proxy" in tpl
    assert "trap on_error ERR" in tpl
    assert "User=zt-provisioner" in tpl
    assert "NoNewPrivileges=true" in tpl
    assert "PrivateTmp=true" in tpl
    assert "ProtectSystem=strict" in tpl
    assert "ProtectHome=true" in tpl
    assert "CapabilityBoundingSet=" in tpl
    assert "RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX" in tpl
    assert "AUDIT_KMS_KEY_ID" in tpl
    assert "AUDIT_LOG_GROUP_NAME" in tpl


def test_bootstrap_has_self_healing_logic():
    tpl = (ROOT / "terraform/user-data.sh.tpl").read_text()
    for token in [
        "retry()",
        "heal_dpkg()",
        "ensure_service_active()",
        "record_heal",
        "write_state",
        "SELF_HEALING_ATTEMPTS",
        "require_command",
        "cleanup_paths",
        "wait_for_service_active",
        "wait_for_file",
    ]:
        assert token in tpl


def test_policy_guardrails_are_wired():
    makefile = (ROOT / "Makefile").read_text()
    ci = (ROOT / ".github/workflows/ci.yml").read_text()
    assert ".checkov.yml" in [p.name for p in ROOT.iterdir()]
    assert ".tfsec.yml" in [p.name for p in ROOT.iterdir()]
    assert "policy:" in makefile
    assert "scripts/policy-scan.sh" in makefile
    assert "verify:" in makefile
    assert "bridgecrewio/checkov-action@9201a8e6eaa919e3444d7c4ca691896efde4f033" in ci
    assert "aquasecurity/tfsec-action@b466648d6e39e7c75324f25d83891162a721f2d6" in ci
    assert "github/codeql-action/analyze@e46ed2cbd01164d986452f91f178727624ae40d7" in ci
    assert "anchore/sbom-action@e22c389904149dbc22b58101806040fa8d37a610" in ci


def test_public_repo_governance_files_exist():
    required = [
        "LICENSE",
        "SECURITY.md",
        "CONTRIBUTING.md",
        "CODE_OF_CONDUCT.md",
        ".github/dependabot.yml",
        ".github/PULL_REQUEST_TEMPLATE.md",
        ".github/ISSUE_TEMPLATE/bug_report.md",
        ".github/ISSUE_TEMPLATE/feature_request.md",
        "docs/STATUS.md",
        "docs/DEMO_NARRATIVE.md",
    ]
    missing = [p for p in required if not (ROOT / p).exists()]
    assert not missing


def test_public_docs_do_not_include_known_sensitive_disclosures():
    forbidden = [
        "AWSAdministratorAccess-" + "014148" + "916722",
        "014148" + "916722",
        "zt-infra-v2/" + "tailscale-auth-key",
        "/Users/" + "oscarmack",
        "0x73D7465a33906156447C8D8bf4ad285dCd811" + "fD2",
        "0x9bd34a4656075869f72f4a5a9fb016c4cb4c9cf0db19b27383e787192b6b" + "ecf9",
        "0xd5f725ca0531e0eb6c8754e62c94d7c027e1b58cc72d541d4c288e9b297a7" + "e3f",
        "0xc0fd34C1d7bbFDCFc46D40Ffd085c3BF6ef67" + "b56",
    ]
    scan_paths = [
        "README.md",
        ".env.example",
        "AGENTS.md",
        "docs",
        "scripts",
        "terraform",
        "provisioner/src",
    ]
    haystack = []
    for path in scan_paths:
        full_path = ROOT / path
        if full_path.is_dir():
            for child in full_path.rglob("*"):
                if child.is_file() and child.suffix in {".md", ".json", ".yaml", ".yml", ".sh", ".tf", ".py", ".js", ".tpl", ".example"}:
                    haystack.append(child.read_text(errors="ignore"))
        elif full_path.exists():
            haystack.append(full_path.read_text(errors="ignore"))
    combined = "\n".join(haystack)
    leaked = [token for token in forbidden if token in combined]
    assert not leaked


def test_compliance_controls_are_wired():
    makefile = (ROOT / "Makefile").read_text()
    main_tf = (ROOT / "terraform/main.tf").read_text()
    outputs_tf = (ROOT / "terraform/outputs.tf").read_text()
    cloudwatch_tf = (ROOT / "terraform/modules/cloudwatch/main.tf").read_text()
    guardduty_tf = (ROOT / "terraform/modules/guardduty/main.tf").read_text()
    evidence_script = (ROOT / "scripts/collect-evidence.sh").read_text()
    soc2_mapping = (ROOT / "policies/soc2-terraform-controls.yml").read_text()

    for token in [
        'module "guardduty"',
        'module "cloudwatch"',
        "guardduty_detector_id",
        "cloudwatch_dashboard_name",
    ]:
        assert token in main_tf or token in outputs_tf
    for token in [
        "aws_cloudwatch_dashboard",
        "aws_cloudwatch_metric_alarm",
        "aws_cloudwatch_log_metric_filter",
        "StatusCheckFailed",
        "VpcFlowRejectedPackets",
    ]:
        assert token in cloudwatch_tf
    assert "aws_guardduty_detector" in guardduty_tf
    assert "evidence:" in makefile
    for token in [
        "aws guardduty get-detector",
        "aws cloudwatch get-dashboard",
        "aws kms describe-key",
        "aws logs get-log-events",
        "aws ec2 describe-security-groups",
        "make policy",
        "manifest.json",
    ]:
        assert token in evidence_script
    for control_id in ["CC6.1", "CC6.6", "CC7.2", "CC7.3", "CC8.1", "A1.2"]:
        assert control_id in soc2_mapping


def test_agent_control_plane_is_wired():
    server = (ROOT / "provisioner/src/server.js").read_text()
    audit = (ROOT / "provisioner/src/audit.js").read_text()
    policy = (ROOT / "provisioner/src/policy.js").read_text()
    package_json = (ROOT / "provisioner/package.json").read_text()
    actions_policy = (ROOT / "provisioner/policies/actions.json").read_text()
    main_tf = (ROOT / "terraform/main.tf").read_text()

    for token in [
        'app.post("/actions"',
        "evaluateAction(policy",
        "auditor.record",
        "resource",
        "decision === \"allow\" ? 200 : 403",
    ]:
        assert token in server
    for token in [
        "previous_hash",
        "current_hash",
        "resource",
        "ECDSA_SHA_256",
        "SignCommand",
        "PutLogEventsCommand",
        "audit-chain.jsonl",
    ]:
        assert token in audit
    assert "defaultDecision" in policy
    assert "aws.ec2.terminate_instances" in actions_policy
    assert "mcp.github.create_pull_request" in actions_policy
    assert "openai.agents.tool.github.create_pull_request" in actions_policy
    assert "a2a.github_agent.send_message" in actions_policy
    assert "@aws-sdk/client-kms" in package_json
    assert "@aws-sdk/client-cloudwatch-logs" in package_json
    for token in [
        'resource "aws_kms_key" "audit_signing"',
        'key_usage                = "SIGN_VERIFY"',
        'resource "aws_cloudwatch_log_group" "agent_audit"',
        'resource "aws_iam_role_policy" "agent_audit"',
        '"logs:PutLogEvents"',
        '"kms:Sign"',
    ]:
        assert token in main_tf


def test_langgraph_plugin_is_wired():
    client = (ROOT / "zt_langgraph/client.py").read_text()
    nodes = (ROOT / "zt_langgraph/nodes.py").read_text()
    docs = (ROOT / "docs/LANGGRAPH_PLUGIN.md").read_text()
    example = (ROOT / "examples/langgraph_control_plane_demo.py").read_text()
    makefile = (ROOT / "Makefile").read_text()

    for token in [
        "ControlPlaneClient",
        "/actions",
        "HTTPError",
        "decision",
    ]:
        assert token in client
    for token in [
        "create_policy_decision_node",
        "create_guarded_action_node",
        "route_by_decision",
        'decision["decision"] != "allow"',
    ]:
        assert token in nodes
    for token in [
        "StateGraph",
        "add_conditional_edges",
        "policy_gate",
    ]:
        assert token in docs
        assert token in example
    assert "tests/test_langgraph_plugin.py" in makefile


def test_openai_assistants_wrapper_is_wired():
    wrapper = (ROOT / "zt_openai/assistants.py").read_text()
    docs = (ROOT / "docs/OPENAI_ASSISTANTS_ZERO_TRUST_WRAPPER.md").read_text()
    makefile = (ROOT / "Makefile").read_text()
    readme = (ROOT / "README.md").read_text()

    for token in [
        "ZeroTrustAssistantsWrapper",
        "required_action.submit_tool_outputs.tool_calls",
        "submit_tool_outputs",
        "control_plane.decide",
        'decision["decision"] != "allow"',
        "ToolRegistry",
    ]:
        assert token in wrapper
    for token in [
        "OpenAI Assistants API",
        "Responses API",
        "policy boundary",
        "fail closed",
    ]:
        assert token in docs
    assert "tests/test_openai_assistants_wrapper.py" in makefile
    assert "OpenAI interoperability" in readme


def test_openai_responses_wrapper_is_wired():
    wrapper = (ROOT / "zt_openai/responses.py").read_text()
    docs = (ROOT / "docs/OPENAI_RESPONSES_ZERO_TRUST_WRAPPER.md").read_text()
    makefile = (ROOT / "Makefile").read_text()
    readme = (ROOT / "README.md").read_text()

    for token in [
        "ZeroTrustResponsesWrapper",
        'type") == "function_call"',
        "function_call_output",
        "control_plane.decide",
        'decision["decision"] != "allow"',
        "continue_response",
    ]:
        assert token in wrapper
    for token in [
        "Responses API",
        "function_call",
        "call_id",
        "function_call_output",
        "reasoning items",
    ]:
        assert token in docs
    assert "tests/test_openai_responses_wrapper.py" in makefile
    assert "ZeroTrustResponsesWrapper" in readme


def test_openai_agents_sdk_guardrail_plugin_is_wired():
    plugin = (ROOT / "zt_openai/agents_sdk.py").read_text()
    docs = (ROOT / "docs/OPENAI_AGENTS_SDK_GUARDRAIL_PLUGIN.md").read_text()
    makefile = (ROOT / "Makefile").read_text()
    readme = (ROOT / "README.md").read_text()

    for token in [
        "AgentsSDKGuardrailPlugin",
        "create_tool_input_guardrail",
        "function_tool_options",
        "ToolGuardrailFunctionOutput",
        "tool_input_guardrail",
        "control_plane.decide",
        "local_guardrail_only",
        "deny_behavior",
    ]:
        assert token in plugin
    for token in [
        "OpenAI Agents SDK",
        "ToolContext.tool_name",
        "ToolContext.tool_arguments",
        "reject_content",
        "raise_exception",
        "fail closed",
    ]:
        assert token in docs
    assert "tests/test_openai_agents_sdk_guardrail.py" in makefile
    assert "AgentsSDKGuardrailPlugin" in readme


def test_mcp_zero_trust_gateway_is_wired():
    gateway = (ROOT / "zt_mcp/gateway.py").read_text()
    docs = (ROOT / "docs/MCP_ZERO_TRUST_GATEWAY.md").read_text()
    makefile = (ROOT / "Makefile").read_text()
    readme = (ROOT / "README.md").read_text()

    for token in [
        "MCPZeroTrustGateway",
        '"tools/call"',
        "control_plane.decide",
        "resource",
        "isError",
        "structuredContent",
        "local_gateway_only",
    ]:
        assert token in gateway
    for token in [
        "agent -> MCP client -> Zero Trust MCP Gateway",
        "tools/call",
        "mcp.github.create_pull_request",
        "KMS signature",
        "fail closed",
    ]:
        assert token in docs
    assert "tests/test_mcp_zero_trust_gateway.py" in makefile
    assert "MCP Zero Trust Gateway" in readme


def test_a2a_policy_proxy_is_wired():
    proxy = (ROOT / "zt_a2a/proxy.py").read_text()
    docs = (ROOT / "docs/A2A_POLICY_PROXY.md").read_text()
    makefile = (ROOT / "Makefile").read_text()
    readme = (ROOT / "README.md").read_text()

    for token in [
        "A2APolicyProxy",
        "SendMessage",
        "SendStreamingMessage",
        "CancelTask",
        "TASK_STATE_REJECTED",
        "control_plane.decide",
        "local_proxy_only",
    ]:
        assert token in proxy
    for token in [
        "A2A Policy Proxy",
        "a2a.github_agent.send_message",
        "TASK_STATE_REJECTED",
        "TASK_STATE_AUTH_REQUIRED",
        "fail closed",
    ]:
        assert token in docs
    assert "tests/test_a2a_policy_proxy.py" in makefile
    assert "A2A Policy Proxy" in readme


def test_interoperability_demo_contract_is_documented():
    test_file = (ROOT / "tests/test_interoperability_demo_contract.py").read_text()
    docs = (ROOT / "docs/INTEROPERABILITY_DEMO.md").read_text()
    slide = (ROOT / "docs/presentations/agent_interoperability_demo_slide.md").read_text()
    appendix = (ROOT / "docs/presentations/agent_interoperability_appendix.md").read_text()
    makefile = (ROOT / "Makefile").read_text()
    readme = (ROOT / "README.md").read_text()

    for token in [
        "test_langgraph_agent_blocked",
        "test_openai_responses_agent_blocked",
        "test_mcp_tool_call_blocked",
        "test_a2a_external_agent_task_rejected",
        "test_all_demo_interfaces_share_signed_audit_record_format",
        "assert_signed_audit_record",
    ]:
        assert token in test_file
    for token in [
        "LangGraph agent blocked",
        "OpenAI Responses agent blocked",
        "MCP tool call blocked",
        "A2A external agent task rejected",
        "same signed audit record format",
    ]:
        assert token in docs
        assert token in slide
        assert token in appendix
    assert "tests/test_interoperability_demo_contract.py" in makefile
    assert "Interoperability demo contract" in readme


def test_fetch_logs_avoids_eval_and_uses_ssm_send_command():
    script = (ROOT / "scripts/fetch-logs.sh").read_text()
    assert "eval " not in script
    assert "wait_for_ssm" in script
    assert "describe-instance-information" in script
    assert "aws ssm send-command" in script
    assert "aws ssm wait command-executed" in script


def test_windows_powershell_operator_scripts_are_wired():
    scripts = {
        path.name: path.read_text()
        for path in (ROOT / "scripts/windows").glob("*.ps1")
    }
    required = {
        "ZtCommon.ps1",
        "Test-ZtPreflight.ps1",
        "New-ZtTailscaleSecret.ps1",
        "Invoke-ZtStatic.ps1",
        "Invoke-ZtPolicy.ps1",
        "Invoke-ZtDeploy.ps1",
        "Invoke-ZtLive.ps1",
        "Get-ZtLogs.ps1",
        "Remove-ZtDeployment.ps1",
    }
    assert required <= set(scripts)
    assert "Set-ZtAwsEnvironment" in scripts["ZtCommon.ps1"]
    assert "Assert-ZtTailscaleAuthKey" in scripts["ZtCommon.ps1"]
    assert '"sts" "get-caller-identity"' in scripts["Test-ZtPreflight.ps1"]
    assert '"secretsmanager" "create-secret"' in scripts["Test-ZtPreflight.ps1"]
    assert '"secretsmanager" "put-secret-value"' in scripts["New-ZtTailscaleSecret.ps1"]
    assert 'terraform "apply" "-auto-approve"' in scripts["Invoke-ZtDeploy.ps1"]
    assert "tests/test_live_integration.py" in scripts["Invoke-ZtLive.ps1"]
    assert "AWS-RunShellScript" in scripts["Get-ZtLogs.ps1"]
    assert "command-executed" in scripts["Get-ZtLogs.ps1"]
    assert "zt-verify.json" in scripts["Get-ZtLogs.ps1"]
    assert "ConfirmDestroy" in scripts["Remove-ZtDeployment.ps1"]

    runbook = (ROOT / "docs/windows-poc/AWS_POWERSHELL_POC.md").read_text()
    assert "without WSL2" in runbook
    assert "AWS CLI v2" in runbook
    assert "nono_wfp" in runbook
