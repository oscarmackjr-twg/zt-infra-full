# Contributing

ZT-Infra v2 is a security-focused reference implementation. Contributions should keep the project buildable, auditable, and explicit about what is production-ready versus experimental.

## Development Setup

```bash
cd zt-infra-v2
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
```

Set your own AWS profile, account ID, and secret names in `.env`. Do not commit `.env`, evidence bundles, Terraform state, generated keys, logs, or provider credentials.

## Before Opening A PR

Run:

```bash
make static
make policy
make github-ready
```

If your change touches the Node provisioner, also run:

```bash
cd provisioner
npm install
npm test
```

## Coding Standards

- Fail closed on policy and provider errors.
- Keep public ingress disabled.
- Keep SSM fallback working.
- Make bootstrap scripts idempotent and observable.
- Keep secrets in AWS Secrets Manager or local ignored files, never in source.
- Prefer explicit structured JSON over free-form logs for verification outputs.
- Add focused tests for behavior changes.
- Keep documentation accurate and avoid publishing real account IDs, ARNs, wallet addresses, transaction hashes, local paths, or customer-specific details.

## Review Structure

Security-sensitive changes require review for:

- authorization behavior
- audit record shape and tamper evidence
- Terraform/IAM blast radius
- bootstrap rollback and failure visibility
- public disclosure risk

## Contribution Areas

Useful contribution areas:

- new execution brokers
- policy templates
- interoperability adapters
- verifier CLI improvements
- Terraform guardrails
- documentation that clarifies secure operation

Avoid adding marketing or launch-planning artifacts to the infrastructure repo.
