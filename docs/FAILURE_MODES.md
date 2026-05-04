# Production Failure Modes

This MVP is intentionally small, but it still needs predictable failure behavior.
The table below lists the primary production failure modes and the current
mitigation in this repository.

| Failure mode | Impact | Mitigation |
|---|---|---|
| Missing AWS credentials or wrong account/region | Terraform can deploy to the wrong place or fail mid-run | Terraform variable validation, EC2 lifecycle preconditions, and `make preflight` require an explicit AWS profile and can pin an operator-provided `allowed_aws_account_id` plus region `us-east-2`. |
| Missing or malformed Tailscale auth key | EC2 boots but cannot join tailnet | `scripts/preflight.sh` validates the current secret format before deploy; bootstrap classifies rejected keys as `tailscale-auth-key=invalid` in `/var/log/zt-verify.json`. |
| Rotated Tailscale key does not rebootstrap EC2 | `make deploy` reports no changes while instance still has failed state | Terraform renders the non-secret Secrets Manager version ID into user data, forcing replacement when the secret rotates. |
| Expired, revoked, or single-use Tailscale key | Tailnet join fails even if format is valid | Bootstrap fails fast, preserves SSM access, keeps nginx and `zt-provisioner` active locally, and writes failure JSON. Rotate with a fresh reusable key and run `make deploy`. |
| Tailscale Serve CLI syntax changes across versions | Host joins Tailscale but HTTPS serving fails | Bootstrap probes current and legacy Serve syntaxes, validates `tailscale serve status --json`, and records selected syntax plus errors. |
| Tailscale Serve prerequisites missing in tailnet | HTTPS URL is unavailable | Detector records Serve errors in verify JSON; live tests fail before accepting incomplete deployment. |
| SSM agent missing or delayed | No fallback access after failed Tailscale join | Bootstrap installs or enables SSM, waits for service readiness, and `fetch-logs` waits for SSM Online. |
| Public inbound access accidentally added | Zero Trust boundary is broken | Terraform security group ingress is empty; default security group is locked down; static and live tests assert no ingress. |
| Over-broad public egress | Larger blast radius if instance is compromised | Egress is scoped to DNS, HTTP/HTTPS bootstrap dependencies, Tailscale UDP, and AWS time sync; tfsec suppressions document intentional MVP exceptions. |
| IMDSv1 enabled | Credential theft risk through SSRF-style paths | Terraform requires IMDSv2; live tests assert `HttpTokens=required`. |
| Unencrypted root volume | Data exposure risk on snapshot or volume leakage | Terraform encrypts the root volume; live tests assert all attached EBS volumes are encrypted. |
| apt/dpkg locks during cloud-init | Bootstrap fails nondeterministically | Bootstrap waits for apt locks, retries `dpkg --configure -a`, and records attempts. |
| Network-dependent install flake | Partial bootstrap or missing services | Bootstrap retries apt, AWS CLI download, Tailscale install, npm install, secret fetch, and service readiness. |
| Service starts slowly or crashes during bootstrap | Verify JSON reports false success | Bootstrap enables, restarts, and waits for nginx, tailscaled, SSM, and `zt-provisioner` before success. |
| Verify log missing on failure | Operators cannot diagnose without console access | `ERR` trap writes `/var/log/zt-bootstrap-state.json` and `/var/log/zt-verify.json` on failure. |
| `make fetch-logs` races SSM or cloud-init | Log retrieval fails or captures incomplete state | Fetch script waits for SSM Online and waits for non-empty verify JSON. |
| Accidental `make destroy` | Production environment deleted by typo | `scripts/destroy.sh` requires `CONFIRM_DESTROY=zt-infra-v2`. |
| Terraform state, keys, or logs committed | Secrets or infrastructure internals leak to GitHub | `.gitignore` excludes generated artifacts; `make github-ready` scans source and tracked files. |
| CI misses bootstrap regressions | Shell/user-data bugs ship unnoticed | GitHub Actions runs static tests and bootstrap simulation tests. |
| Local Checkov/tfsec not installed | Policy checks silently absent locally | `make policy` warns locally; CI runs both scanners. |
| CDP Server Wallet unavailable | DAAL transaction cannot be submitted immediately | Local audit remains durable; DAAL record stays `pending` or `failed`; retry/reconciliation can submit later. |
| Alchemy RPC unavailable | Receipt verification cannot confirm transaction status | Authorization and local audit continue; switch RPC provider or retry reconciliation. |
| thirdweb unavailable | Contract deployment or optional Engine write path is unavailable | CDP direct mode remains the MVP runtime path; deployment tasks wait until thirdweb recovers or another EVM deployment tool is used. |
| Base Sepolia congestion or outage | DAAL transaction confirmation is delayed | Authorization does not wait on ledger finality; batch queue and local system of record remain authoritative until reconciliation. |

## Recovery Commands

Rotate a rejected Tailscale key:

```bash
./scripts/create-tailscale-secret.sh "$TAILSCALE_SECRET_NAME" 'tskey-auth-REPLACE_ME'
make deploy
make verify
```

Fetch live diagnostics:

```bash
make fetch-logs
cat logs/zt-verify.json
```

Destroy intentionally:

```bash
CONFIRM_DESTROY=zt-infra-v2 make destroy
```
