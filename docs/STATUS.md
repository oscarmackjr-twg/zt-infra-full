# Status

This file tracks volatile deployment status without putting live account IDs, wallet addresses, transaction hashes, or host identifiers in the README.

## Current MVP

- AWS MVP path: implemented.
- No-public-ingress Terraform posture: implemented.
- SSM fallback: implemented.
- Tailscale Serve verification: implemented.
- Agent action decision API: implemented.
- KMS-signed, hash-chained audit records: implemented.
- LangGraph/OpenAI/MCP/A2A interoperability adapters: implemented.
- Optional DAAL hash anchoring: implemented as an MVP integration.

## Evidence Handling

Public documentation should use placeholders for:

- AWS account IDs
- ARNs and KMS key IDs
- EC2 instance IDs
- Tailscale secret names tied to a real account
- DAAL contract addresses
- wallet addresses
- transaction hashes
- local filesystem paths

Reviewed evidence bundles may include those details privately or in a release artifact only after an explicit disclosure decision.

## Production Gaps

- Remote Terraform state and locking.
- Private VPC endpoints for SSM and Secrets Manager.
- Scheduled DAAL reconciliation and alerting for stuck attestations.
- Mainnet DAAL operating runbook.
- Signed release provenance.
