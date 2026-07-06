# zt-infra-full

An open adapter contract and audit envelope for agent action authorization, with a full AWS reference implementation.

ZT-Infra sits between agent frameworks and execution environments. It answers one narrow question before a tool call runs: **is this agent allowed to take this action on this resource right now?** The project defines the request shape, fail-closed response semantics, broker handoff, and signed audit record so LangGraph, OpenAI wrappers, MCP, A2A, and custom agent runtimes do not each invent their own authorization pattern.

If you are integrating as an application developer, start with the five-minute starter repo: [zt-adapter-hello-world](https://github.com/oscarmackjr-twg/zt-adapter-hello-world). This repository is the full AWS MVP implementation for operators who want to deploy and verify the reference control plane.

## Why This Exists

Autonomous agents are beginning to discover tools, call APIs, and trigger infrastructure changes. Existing security primitives are strong, but they live at different layers: SPIFFE/SPIRE for workload identity, OPA or Cedar for policy decisions, nono or microVMs for containment, and SIEM tooling for operations. ZT-Infra is the integration layer that turns those primitives into one agent-shaped control point.

The goal is not to replace those systems. ZT-Infra provides the adapter contract and audit envelope around them: a stable `POST /actions` API, common deny/allow response semantics, pre-execution broker handoff, and hash-chained audit evidence that every integration can share.

The longer-term vision is a standard shape for agent action authorization, similar in spirit to what OCI did for containers: a practical contract that lets many runtimes, policy engines, sandboxes, and observability stacks interoperate.

## What It Proves

Agent authorization:

- `POST /actions` denies unauthorized agent actions before execution.
- Agent decisions are hash-chained, signed with AWS KMS, and written to CloudWatch Logs.
- Policy enforcement happens before execution broker handoff.
- LangGraph, OpenAI, MCP, and A2A integrations use the same decision and audit shape.
- Optional DAAL anchoring submits only action hashes to an EVM-compatible ledger asynchronously.

Operational hardening:

- Terraform creates an AWS VPC and Ubuntu 24.04 EC2 instance with no public inbound access.
- Operators use AWS SSM Session Manager and Tailscale rather than public SSH.
- Nginx and the `zt-provisioner` service are exposed only through the private access path.
- Bootstrap writes `/var/log/zt-bootstrap.log` and `/var/log/zt-verify.json` for recovery.
- GuardDuty, CloudWatch alarms, VPC Flow Logs, and compliance evidence collection are wired into the deployment.

See [docs/PROJECT_SCOPE.md](docs/PROJECT_SCOPE.md) and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the layer model and system diagram.

## How It Fits

| Layer | Typical tools | ZT-Infra role |
| --- | --- | --- |
| Identity | SPIFFE/SPIRE, NANDA-style cross-org identity, Tailscale identity | Consume identity and bind it to the action actor. |
| Policy | OPA, Cedar, local JSON policy | Normalize agent actions into one policy decision contract. |
| Execution containment | nono, Docker, gVisor, Firecracker, Kata, browser sandboxes | Hand approved work to a broker and fail closed before dispatch. |
| Audit and observability | CloudWatch, SIEM, OpenTelemetry, DAAL hash anchoring | Emit the same signed audit envelope from every integration. |

## Trying It Without AWS

The fastest path is the public starter repo:

```bash
git clone https://github.com/oscarmackjr-twg/zt-adapter-hello-world.git
cd zt-adapter-hello-world
docker compose up
```

That flow shows a mock agent being denied, then authorized after policy changes, without requiring an AWS account.

## AWS Quickstart

Install local prerequisites:

- Terraform
- AWS CLI
- Python 3.12+
- Node.js 20+
- `jq`

Clone and prepare this repository:

```bash
git clone https://github.com/oscarmackjr-twg/zt-infra-full.git
cd zt-infra-full
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
```

Edit `.env` with your own AWS profile, AWS account ID, region, and Secrets Manager name. `.env` is ignored by Git.

Example operator configuration:

```bash
export AWS_PROFILE=<YOUR_AWS_PROFILE>
export AWS_REGION=us-east-2
export TF_VAR_allowed_aws_account_id=<YOUR_12_DIGIT_AWS_ACCOUNT_ID>
export TAILSCALE_SECRET_NAME=<YOUR_PROJECT>/tailscale-auth-key
```

Create or update the Tailscale auth key secret:

```bash
./scripts/create-tailscale-secret.sh "$TAILSCALE_SECRET_NAME" 'tskey-auth-REPLACE_ME'
```

Run the local checks:

```bash
make static
make policy
```

Deploy and verify:

```bash
make preflight
make deploy
make live
make fetch-logs
```

The deployed host should produce:

- `/var/log/zt-bootstrap.log`
- `/var/log/zt-verify.json`
- active SSM connectivity
- active Tailscale connectivity
- active Nginx
- active `zt-provisioner`
- no public inbound security group rules

Windows operators can use the native PowerShell runbook for the same flow:

- [docs/windows-poc/AWS_POWERSHELL_POC.md](docs/windows-poc/AWS_POWERSHELL_POC.md)

That runbook also records the current Windows `nono` client verification path.
After the AWS backend is healthy, a Windows endpoint joined to the same tailnet
can verify private Tailscale reachability, `nono-wfp-service` health, confined
process launch, and `nono why` policy reasoning for outbound network allowed
vs. `--block-net` denied. Domain-specific `--allow-domain` proxy filtering is
not implemented for Windows supervised execution in `nono v0.66.1`; unsupported
proxy-filter flows fail closed.

## Local Provisioner

You can run the Node service locally for API development:

```bash
cd provisioner
npm install
npm start
curl http://127.0.0.1:3000/health
```

Policy decision demo:

```bash
curl -sS -X POST http://127.0.0.1:3000/actions \
  -H 'content-type: application/json' \
  -d '{"actor":"demo-agent","action":"aws.ec2.terminate_instances"}' | jq .
```

Expected result:

- `decision` is `deny`
- `reason` explains why the action is blocked
- `audit.previous_hash` and `audit.current_hash` are SHA-256 hashes
- `audit.kms_signature.algorithm` is `ECDSA_SHA_256` when AWS KMS signing is configured

## Infrastructure

Terraform creates:

- VPC, subnet, route table, and internet gateway for outbound-only bootstrap access
- locked-down security group with no ingress rules
- IAM role and instance profile for SSM and scoped secret retrieval
- GuardDuty detector
- CloudWatch dashboard, alarms, VPC Flow Log metrics, and encrypted log groups
- asymmetric KMS key for agent audit signatures
- generated EC2 key pair written under `out/`
- Ubuntu 24.04 EC2 instance

Production operators should replace local Terraform state with an S3 backend before shared use. Current Terraform S3 backends should use S3 lockfiles (`use_lockfile = true`) rather than deprecated DynamoDB locking.

## Agent Integrations

The same `POST /actions` contract is used by:

- `zt_langgraph` for LangGraph policy gates
- `zt_openai` for OpenAI interoperability across `AgentsSDKGuardrailPlugin`, `ZeroTrustResponsesWrapper`, and Assistants compatibility
- `zt_mcp` for the MCP Zero Trust Gateway and MCP `tools/call` interception
- `zt_a2a` for the A2A Policy Proxy

Primary docs:

- [docs/LANGGRAPH_PLUGIN.md](docs/LANGGRAPH_PLUGIN.md)
- [docs/OPENAI_AGENTS_SDK_GUARDRAIL_PLUGIN.md](docs/OPENAI_AGENTS_SDK_GUARDRAIL_PLUGIN.md)
- [docs/OPENAI_RESPONSES_ZERO_TRUST_WRAPPER.md](docs/OPENAI_RESPONSES_ZERO_TRUST_WRAPPER.md)
- [docs/MCP_ZERO_TRUST_GATEWAY.md](docs/MCP_ZERO_TRUST_GATEWAY.md)
- [docs/A2A_POLICY_PROXY.md](docs/A2A_POLICY_PROXY.md)
- [docs/INTEROPERABILITY_DEMO.md](docs/INTEROPERABILITY_DEMO.md)

The Interoperability demo contract verifies:

- LangGraph agent blocked
- OpenAI Responses agent blocked
- MCP tool call blocked
- A2A external agent task rejected
- all four surfaces return the same signed audit record format

## DAAL

DAAL is optional. It anchors action hashes to an EVM-compatible ledger for non-repudiation without sending prompts, chat content, raw tool payloads, or customer data to the chain.

Runtime behavior:

- local authorization returns without waiting for ledger confirmation
- attestations queue locally first
- batched anchoring is supported
- failed ledger submissions remain visible as pending or failed local records

For setup and status tracking, see:

- [docs/DAAL.md](docs/DAAL.md)
- [docs/ENTERPRISE_READINESS.md](docs/ENTERPRISE_READINESS.md)
- [docs/STATUS.md](docs/STATUS.md)

Do not publish real contract addresses or transaction hashes in README-style operator documentation unless deployer wallet linkage has been approved for public release.

## Compliance Evidence

After a successful deployment:

```bash
make evidence
```

The collector writes a timestamped local bundle under `evidence/` with Terraform outputs, EC2 posture, security groups, SSM status, GuardDuty detector state, CloudWatch dashboard definition, KMS/log metadata, policy output, and remote verification logs. Evidence bundles are ignored by Git.

The SOC 2 mapping is intentionally generic and lives in:

- [policies/soc2-terraform-controls.yml](policies/soc2-terraform-controls.yml)
- [docs/SOC2_CONTROL_MAPPING.md](docs/SOC2_CONTROL_MAPPING.md)

## Tooling Notes

The root `package.json` exists for DAAL deployment and Web3 helper tooling. The runtime provisioner service has its own package files under `provisioner/`.

Python adapter modules in this repository are source-level integration examples and tests. Application developers should use [zt-adapter-hello-world](https://github.com/oscarmackjr-twg/zt-adapter-hello-world) as the SDK-facing starter until separately versioned packages are published.

## Publishing Guardrails

Before pushing or publishing:

```bash
make github-ready
gitleaks detect --source . --log-opts="--all" --no-banner
trufflehog git file://. --since-commit="$(git rev-list --max-parents=0 HEAD)" --no-update
```

Review any prior commits that may contain account IDs, wallet addresses, transaction hashes, local paths, generated evidence, logs, or Terraform state.

## Contributing

Start with [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md), and the issue tracker. Good first contributions are usually adapter conformance tests, policy templates, broker documentation, and clearer verifier output.

Before opening a pull request, run:

```bash
make static
make policy
make github-ready
```

Private security issues should follow [SECURITY.md](SECURITY.md), not public GitHub issues.

## Project Files

- [AGENTS.md](AGENTS.md) is the operating guide for coding agents working in this repo.
- [docs/DEMO_NARRATIVE.md](docs/DEMO_NARRATIVE.md) contains the investor/demo narrative, kept under docs rather than at the repo root.
- [docs/PUBLIC_READINESS_CHECKLIST.md](docs/PUBLIC_READINESS_CHECKLIST.md) records the current public-release review checklist and remediation status.

## License

Apache-2.0. See [LICENSE](LICENSE).
