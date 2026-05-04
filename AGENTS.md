# AGENTS.md — Codex Operating Guide for zt-infra-v2

You are working in the `zt-infra-v2` repository. Treat this repo as a Dark Factory MVP: it must be buildable, deployable, verifiable, and recoverable with minimal operator intervention and without logging into the AWS Console.

## Mission

Build and harden a Zero Trust AWS MVP that provisions:

- A fresh AWS VPC in `us-east-2`
- One Ubuntu 24.04 EC2 instance created by Terraform
- No public inbound access
- AWS SSM Session Manager fallback access
- Tailscale control-plane access
- Nginx landing page exposed through Tailscale Serve only
- Node/Express `zt-provisioner` bound to localhost
- Bootstrap logs at `/var/log/zt-bootstrap.log`
- Verification output at `/var/log/zt-verify.json`

## Fixed environment assumptions

Set these explicitly before live AWS work:

```bash
export AWS_PROFILE=<YOUR_AWS_PROFILE>
export AWS_REGION=us-east-2
export TF_VAR_allowed_aws_account_id=<YOUR_12_DIGIT_AWS_ACCOUNT_ID>
```

Default Tailscale secret:

```bash
Set `TAILSCALE_SECRET_NAME` to a Secrets Manager secret under your own project namespace, for example `<YOUR_PROJECT>/tailscale-auth-key`.
```

## Non-negotiable constraints

1. Do not add public inbound security group rules.
2. Do not expose Nginx or `zt-provisioner` directly to the public internet.
3. Do not require SSH for normal operations.
4. Keep SSM access working at all times.
5. Keep bootstrap idempotent and fail-fast.
6. Do not reintroduce runtime Rust compilation unless explicitly required.
7. Do not commit generated keys, state files, `.terraform`, logs, `.env`, or ZIPs.
8. Do not require AWS Console actions for the happy path.
9. Prefer repair/retry logic over manual operator intervention.
10. Make failures observable through logs and JSON status files.

## Required workflow

Before making infrastructure changes:

```bash
make static
make policy
```

Before live deployment:

```bash
make preflight
```

Deploy and verify:

```bash
make deploy
make live
make fetch-logs
```

Destroy when done:

```bash
make destroy
```

## How to work in this repo

Work in phases. Do not skip phases unless a previous run already completed them and the files are unchanged.

### Phase 1 — Static validation

- Inspect Terraform for syntax, variables, outputs, provider versions, and lifecycle behavior.
- Inspect shell scripts for `set -euo pipefail`, quoting, missing dependencies, and safe defaults.
- Inspect Node service for health endpoints and localhost-only binding.
- Run `make static`.

### Phase 2 — Policy-as-code validation

- Run `make policy`.
- Fix Terraform issues rather than suppressing them.
- Suppress only when the design is intentional and document the reason inline.
- Never suppress public ingress findings by adding public ingress.

### Phase 3 — Infrastructure hardening

- Verify VPC, subnet, routing, IAM, instance profile, IMDSv2, encrypted root volume, and SSM role attachment.
- Verify Terraform uses `user_data_replace_on_change = true`.
- Verify every AWS resource has project tags where practical.

### Phase 4 — Bootstrap hardening

- Keep bootstrap self-healing:
  - retry apt/dpkg locks
  - retry network-dependent installs
  - restart failed services
  - regenerate verification JSON even on failure
  - write a machine-readable state file
- Keep bootstrap idempotent:
  - repeated execution should not corrupt services
  - package installs should be safe if already installed
  - systemd units should be overwritten deterministically

### Phase 5 — Zero Trust verification

- Verify Tailscale is installed, running, authenticated, and online.
- Detect working `tailscale serve` syntax across versions.
- Verify Nginx and `zt-provisioner` are active.
- Verify no public ingress exists.

### Phase 6 — Live integration

- Use AWS CLI/SSM/Terraform outputs only; avoid AWS Console assumptions.
- Confirm SSM managed instance availability.
- Fetch `/var/log/zt-bootstrap.log` and `/var/log/zt-verify.json` through SSM.
- Confirm JSON fields show expected services and Tailscale state.

## Expected `/var/log/zt-verify.json`

The file should include at least:

```json
{
  "project": "zt-infra-v2",
  "bootstrap": {
    "status": "ok-or-degraded-or-failed",
    "failed_step": "...",
    "self_healing_attempts": []
  },
  "tailscale": {
    "version": "...",
    "hostname": "...",
    "dnsName": "...",
    "online": true
  },
  "serve_syntax": {
    "working": "A-or-B-or-none"
  },
  "services": {
    "nginx": "active",
    "zt_provisioner": "active"
  }
}
```

## When blocked

If AWS credentials, Tailscale auth key, Terraform, or policy tools are missing, stop only after writing a precise remediation command. Prefer adding scripts/tests that make the missing prerequisite obvious next time.

## Change reporting

When editing files, summarize:

- file path
- reason for change
- commands run
- pass/fail result
- remaining risk

## Success criteria

The repo is acceptable when all of these pass:

```bash
make static
make policy
make deploy
make live
make fetch-logs
```

And the deployed host satisfies:

- no public inbound ingress
- SSM reachable
- Tailscale online
- Tailscale Serve configured
- Nginx active
- `zt-provisioner` active
- `/var/log/zt-verify.json` valid JSON
