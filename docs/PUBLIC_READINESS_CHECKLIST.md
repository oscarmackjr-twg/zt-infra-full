# Public Readiness Checklist

This checklist records the current public-release review findings and remediation status for `zt-infra-full`.

## High Severity

| Item | Status | Resolution |
| --- | --- | --- |
| Full-history disclosure scan for prior AWS account ID, DAAL contract address, transaction hashes, and local paths. | Closed | Ran `git log --all -p` targeted grep, `gitleaks detect --log-opts="--all"`, and `trufflehog git` from the first commit. No historical leaks were found. |
| DAAL contract address and deployment artifact audit. | Closed | Scanned source and docs for EVM addresses. Only deterministic test fixture addresses such as `0x000...dEaD`, `0x000...bEEF`, and `0x111...1111` are present. No deployment artifacts under `deployments/`, `broadcast/`, or contract artifact directories are tracked. |
| Legacy `landing/` asset left in the infrastructure repo. | Closed | Removed the legacy landing page from the tracked repository and removed the top-level README note. The public website remains in the separate developer-site repository. |
| Generated artifacts in `provisioner/` or root. | Closed | Verified no tracked `node_modules`, `.env`, `out/`, `coverage/`, logs, deployment artifacts, Terraform state, or `.terraform/` directories. `.gitignore` blocks those classes of files. |
| Thirteen open Dependabot PRs creating a review-noise signal. | Closed | Verified all open PRs were Dependabot-only, closed the initial burst, and reduced Dependabot open PR limits from 5 to 2 per ecosystem. |

## Medium Severity

| Item | Status | Resolution |
| --- | --- | --- |
| Cold "Dark Factory" phrasing in the first sentence. | Closed | Rewrote README lead around the narrower adapter-contract and audit-envelope claim. The full-automation concept is described through operator behavior rather than jargon. |
| Vision split across too many docs. | Closed | Added a `Why This Exists` section to README with the SPIFFE/OPA/Cedar/nono/SIEM layering model and the OCI-style adapter-contract vision. |
| Missing contributor on-ramp from README. | Closed | Added a `Contributing` section linking `CONTRIBUTING.md`, `SECURITY.md`, required checks, and suggested contribution areas. |
| Empty issue tracker lacked newcomer entry points. | Closed | Created three labeled good-first issues: package Python adapters (#17), add Cedar/OPA examples (#16), and improve local policy demo docs (#18). |
| Relationship between `zt-infra-full` and `zt-adapter-hello-world` was unclear. | Closed | Added a top-level callout and a `Trying It Without AWS` section that points developers to the public starter repo. |
| `What It Proves` mixed value proposition and AWS operational facts. | Closed | Split the section into `Agent authorization` and `Operational hardening`. |
| SOC 2 mapping public-safety review. | Closed | Reviewed the mapping. It remains generic and does not publish customer controls, owners, evidence cadence, account identifiers, or internal gaps. |
| `AGENTS.md` public-safety review. | Closed | Reviewed for customer names, private strategy, and unpublished claims. None were present. Updated repository naming. |
| Checkov/tfsec suppression review. | Closed | Confirmed suppressions do not disable public-ingress findings. Suppressions document the no-ingress public-IP MVP tradeoff and single-account GuardDuty boundary. |

## Low Severity

| Item | Status | Resolution |
| --- | --- | --- |
| README name mismatch: `zt-infra-v2` vs `zt-infra-full`. | Closed | Updated README H1, quickstart clone path, AGENTS heading, workflow name, and root package metadata to use `zt-infra-full`. |
| Root `package.json` looked ambiguous. | Closed | Marked it private, named it `zt-infra-full`, added Apache-2.0 metadata, and documented that it exists for DAAL/Web3 helper tooling. |
| Python adapter install path unclear. | Mitigated | README now states the source modules are reference integrations and points SDK users to the starter repository until separately versioned packages are published. |
| Search topics could be broader. | Closed | Added GitHub topics `ai-security`, `agent-authorization`, and `audit-logging`. |

## Clean Build Decision

A new clean build is not required based on the current evidence. The public repository has short fresh history, full-history secret scans are clean, targeted old-leak scans are clean, deployment artifacts are not tracked, and the remaining work is ordinary documentation and contributor-experience hardening.

Create another fresh public build only if one of these becomes true:

- a real credential, account ID, wallet address, transaction hash, local path, or evidence bundle is discovered in public history;
- a public pull-request diff contains leaked material;
- deployment artifacts from Hardhat, Foundry, Terraform, or evidence collection were committed;
- the project owner decides to remove the Dependabot PR history entirely instead of closing or merging those PRs.
