# Current State Summary For External Collateral

Use this page as the source of truth when updating decks, memos, website copy, or first-customer packages.

## One-Sentence Positioning

ZT-Infra is an open adapter contract and audit envelope for agent action authorization, designed to plug into existing identity, policy, sandbox, and observability layers.

## What Works Today

- AWS infrastructure deploys through Terraform in `us-east-2`.
- EC2 access is Zero Trust oriented: no public SSH, SSM fallback, Tailscale access.
- Nginx and `zt-provisioner` run on the instance.
- `/var/log/zt-verify.json` reports bootstrap, Tailscale, serve syntax, service status, and test URL.
- `zt-provisioner` exposes `POST /actions`.
- Local policy evaluation denies unsafe actions such as `aws.ec2.terminate_instances`.
- Audit records include previous/current hashes and KMS signature metadata.
- Audit records can be written to CloudWatch Logs.
- Optional DAAL ledger anchoring queues asynchronously.
- GuardDuty, CloudWatch alarms/dashboard, VPC Flow Logs, and evidence collection have Terraform/script support.
- LangGraph, OpenAI Responses, MCP, and A2A adapters are covered by a shared test contract.
- Public developer repo exists at `https://github.com/oscarmackjr-twg/zt-adapter-hello-world`.

## Current API Contract

```http
POST /actions
content-type: application/json
```

```json
{
  "actor": "demo-agent",
  "action": "aws.ec2.terminate_instances",
  "resource": "i-demo"
}
```

Denied response:

```json
{
  "ok": false,
  "actor": "demo-agent",
  "action": "aws.ec2.terminate_instances",
  "resource": "i-demo",
  "decision": "deny",
  "reason": "Agents may not terminate EC2 instances in the Dark Factory MVP.",
  "audit": {
    "timestamp": "2026-04-30T13:16:18.717Z",
    "previous_hash": "...",
    "current_hash": "...",
    "kms_signature": {
      "algorithm": "ECDSA_SHA_256",
      "key_id": "arn:aws:kms:us-east-2:<AWS_ACCOUNT_ID>:key/...",
      "signature": "..."
    },
    "daal": {
      "status": "disabled-or-queued-or-submitted",
      "actionHash": "0x..."
    }
  }
}
```

## Product Vision

The project is not trying to replace SPIFFE/SPIRE, OPA, Cedar, CSA ATF, nono, microVMs, or SIEM tooling. Its role is to make agent frameworks use those controls through one portable adapter contract. That future requires:

- canonical transient agent identity;
- workload-bound credentials;
- signed agent/runtime attestation;
- trust bundles and federation;
- policy schema versioning;
- conformance tests across frameworks and protocols;
- durable, verifiable audit evidence.

## What To Avoid Saying

- Do not say the MVP is production-certified.
- Do not say the product prevents prompt injection.
- Do not say public quickstart mock signatures are cryptographic production proof.
- Do not say `/authorize` is implemented in the current MVP.
- Do not say every adapter framework version is certified.
- Do not say pricing or SLA terms are validated.
- Do not say ZT-Infra replaces identity providers, policy engines, sandboxes, or governance frameworks.
