# Presentation Package Review

This directory contains investor, first-customer, enterprise, SOC 2, and demo-support artifacts. The packages are draft collateral unless a document explicitly says it is verified.

## Repository Map

Use these repository names consistently:

| Repository | Purpose | Current status |
| --- | --- | --- |
| `oscarmackjr-twg/ZERO_TRUST_V2` | Full private infrastructure and control-plane MVP. Terraform, EC2 bootstrap, Tailscale/SSM access, `zt-provisioner`, KMS-signed audit records, DAAL sidecar, interoperability wrappers, policy tests, and live verification. | Current source of truth for implementation. |
| `oscarmackjr-twg/zt-adapter-hello-world` | Public developer quickstart for adapter authors. Five-minute mock control-plane flow, deny-before-execute demo, allow-after-policy demo, public docs, roadmap, and contribution guidance. | Published public repo, stable tag `v0.1.0`. |
| future developer site repository | Public website/docs site that links to stable releases and quickstarts. | Not created in this repo yet. Treat as planned. |

## Architecture Diagram

Use [../ARCHITECTURE.md](../ARCHITECTURE.md) as the current reviewed architecture reference. It includes:

- the updated architecture diagram;
- Mermaid source for slides and docs systems;
- an SVG asset suitable for websites and presentations.

The diagram started from `zt_first_customer_system_interop_package/05c_first_customer_architecture.drawio`, which was the most complete existing presentation diagram, then was reconciled with the current implementation.

## Current Implementation Facts

The current private MVP implements:

- `POST /actions` in `provisioner/src/server.js`.
- Request body: `actor`, `action`, optional `resource`.
- Response body: `ok`, `actor`, `action`, `resource`, `decision`, `reason`, `audit`.
- Audit envelope: `timestamp`, `previous_hash`, `current_hash`, `kms_signature`, and optional `daal`.
- KMS signing when `AUDIT_KMS_KEY_ID` is configured.
- CloudWatch Logs publishing when `AUDIT_LOG_GROUP_NAME` is configured.
- Optional asynchronous DAAL ledger anchoring; the authorization path does not wait for ledger confirmation.
- Interoperability wrappers for LangGraph, OpenAI Responses, OpenAI Assistants compatibility, MCP, and A2A.
- Cross-interface static proof in `tests/test_interoperability_demo_contract.py`.
- Public developer quickstart in `public_repo_seed/zt-adapter-hello-world`.

The current public developer repo implements:

- local mock `/actions`;
- local mock `/agents` and `/policies/allow` for onboarding only;
- `ZeroTrustClient.decide(...)` and `ZeroTrustClient.guardedCall(...)`;
- helper methods for LangGraph, OpenAI Responses, MCP, and A2A action naming;
- mock signatures marked `MOCK_ECDSA_SHA_256`;
- public Identity & Policy, Threat Model, Roadmap, Security, and Contribution docs.

## Important Accuracy Rules

Use these rules in all decks and docs:

- Say current API endpoint: `POST /actions`.
- Treat `/authorize`, `/identity/token`, `/execute`, and `/audit/query` as future or first-customer API candidates unless they are implemented later.
- Do not describe `interface` or `request_id` as mandatory current audit-envelope fields. They are useful future/customer metadata, not current signed-record fields.
- Say "KMS-signed audit records" for live private infra only when `AUDIT_KMS_KEY_ID` is configured.
- Say "mock signed envelope" or `MOCK_ECDSA_SHA_256` for public quickstart output.
- Say "SOC 2 aligned" or "SOC 2 control mapping," not "SOC 2 certified."
- Say "pilot target" or "design-partner target" for SLA/pricing language.
- Do not claim installed customers, validated pricing, production SLA, or broad framework certification.
- Do not claim ZT-Infra prevents prompt injection. The security boundary is unauthorized tool/action execution.

## Validation Commands

Prefer these commands in reviewed docs:

```bash
make PYTHON=.venv/bin/python static
make policy
make verify
```

For the public developer repo:

```bash
npm test
npm audit --omit=dev
```

Raw `pytest tests/test_interoperability_demo_contract.py` is acceptable only after the Python environment has been prepared.

## Package Status

| Package | Status | Notes |
| --- | --- | --- |
| Root markdown slides and appendices | Reviewed source docs | Updated to current `/actions` and audit-envelope language. |
| `zt_fundable_package_interop` | Reviewed at source-doc level | Binary deck/memo/workbook remain draft collateral. Verify live evidence before external use. |
| `zt_enterprise_ready_interop_package` | Reviewed at source-doc level | Binary contract/SLA/security docs remain draft business documents requiring legal/security review. |
| `zt_first_customer_system_interop_package` | Reviewed at source-doc level | OpenAPI and SDK drafts updated to distinguish current MVP `/actions` from future customer APIs. Binary docs may still need regeneration. |
| SOC 2 and threat-model office files | Draft | Some text predates implemented CloudWatch/GuardDuty/KMS audit work. Use current repo README and Terraform as source of truth. |

## Known Draft Artifact Limitations

- `audit_evidence_binder.docx` could not be read by `textutil`; regenerate it before using externally.
- Office files may still contain old `/authorize` wording because they are binary drafts. Use the Markdown/YAML/SDK files in this directory as the reviewed source layer.
- Pricing workbooks are hypotheses, not customer-validated pricing.
- SLA documents are pilot discussion drafts, not legal commitments.
