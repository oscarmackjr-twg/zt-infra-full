# ZT-Infra v2

ZT-Infra v2 is a Dark Factory reference control plane for agent action authorization on AWS.

It defines the adapter contract around agent tool calls: how an agent asks for authorization, how the system fails closed, how approved work is handed to execution brokers, and how every decision is written as audit evidence. It is designed to compose with existing primitives such as SPIFFE/SPIRE for workload identity, OPA or Cedar for policy engines, nono or microVMs for containment, and SIEM tooling for operations.

This repository contains the full AWS MVP implementation. The public developer starter and website live separately under `public_repo_seed/zt-adapter-hello-world`.

## What It Proves

- Terraform creates an AWS VPC and Ubuntu 24.04 EC2 instance with no public inbound access.
- Operators use AWS SSM Session Manager and Tailscale rather than public SSH.
- Nginx and the `zt-provisioner` service are exposed only through the private access path.
- `POST /actions` denies unauthorized agent actions before execution.
- Agent decisions are hash-chained, signed with AWS KMS, and written to CloudWatch Logs.
- Optional DAAL anchoring submits only action hashes to an EVM-compatible ledger asynchronously.
- LangGraph, OpenAI, MCP, and A2A integrations use the same decision and audit shape.

See [docs/PROJECT_SCOPE.md](docs/PROJECT_SCOPE.md) and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the layer model and system diagram.

## Quickstart

Install local prerequisites:

- Terraform
- AWS CLI
- Python 3.12+
- Node.js 20+
- `jq`

Clone and prepare the repository:

```bash
cd zt-infra-v2
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

Production operators should replace local Terraform state with S3 and DynamoDB locking before shared use.

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

Do not publish real contract addresses or transaction hashes in the README unless the deployer wallet linkage has been approved for public release.

## Compliance Evidence

After a successful deployment:

```bash
make evidence
```

The collector writes a timestamped local bundle under `evidence/` with Terraform outputs, EC2 posture, security groups, SSM status, GuardDuty detector state, CloudWatch dashboard definition, KMS/log metadata, policy output, and remote verification logs. Evidence bundles are ignored by Git.

The SOC 2 mapping lives in:

- [policies/soc2-terraform-controls.yml](policies/soc2-terraform-controls.yml)
- [docs/SOC2_CONTROL_MAPPING.md](docs/SOC2_CONTROL_MAPPING.md)

## Publishing Guardrails

Before pushing or publishing:

```bash
make github-ready
```

This runs static tests, policy scans, and repository disclosure checks. For a public release, also run full-history scanning with official `gitleaks` and `trufflehog` binaries and review any prior commits that may contain account IDs, wallet addresses, transaction hashes, local paths, or generated evidence.

## Project Files

- `AGENTS.md` is the operating guide for coding agents working in this repo.
- `docs/DEMO_NARRATIVE.md` contains demo framing that was previously kept at the repo root.
- `landing/` is a minimal legacy landing-page asset. The public website should remain in its own repository for access-control separation.

## License

Apache-2.0. See [LICENSE](LICENSE).
