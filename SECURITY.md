# Security Policy

ZT-Infra is security-sensitive infrastructure. Please report vulnerabilities privately before opening public issues.

## Reporting

Use one of these channels:

- GitHub private vulnerability reporting, if enabled for this repository.
- Email: `security@zt-infra.org`.

Include:

- affected commit or release
- affected component
- reproduction steps
- impact assessment
- whether secrets, account IDs, wallet addresses, or customer data were exposed

## Scope

In scope:

- policy bypasses in `POST /actions`
- audit-chain tampering or signature misuse
- Terraform that creates public ingress or overbroad IAM
- bootstrap behavior that disables SSM fallback
- accidental disclosure of secrets, account IDs, keys, evidence bundles, or wallet linkages

Out of scope:

- social engineering
- denial-of-service against third-party providers without a ZT-Infra bug
- prompt injection in downstream applications unless it causes ZT-Infra policy bypass
- vulnerabilities in third-party sandboxes, providers, or policy engines not caused by this integration layer

## Response Targets

- Acknowledge: 3 business days.
- Triage: 7 business days.
- Remediation plan: based on severity and exploitability.

Do not include real secrets or exploit payloads in public GitHub issues.
