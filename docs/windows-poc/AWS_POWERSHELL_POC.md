# AWS PowerShell POC Runbook

This runbook is for Windows 10 operators who deploy the AWS-backed
`zt-infra-v2` POC without WSL2. It keeps the cloud target on AWS and replaces
the Bash/Make operator path with native PowerShell scripts.

## Prerequisites

Install these on Windows and ensure each executable is on `PATH`:

- PowerShell 5.1 or PowerShell 7+
- AWS CLI v2
- Terraform
- Python 3.12+
- Node.js 20+
- Git

Optional local policy tools:

- `checkov`
- `tfsec`

## Required Environment

Open PowerShell from the repository root and set:

```powershell
$env:AWS_PROFILE = "<YOUR_AWS_PROFILE>"
$env:AWS_REGION = "us-east-2"
$env:TF_VAR_allowed_aws_account_id = "<YOUR_12_DIGIT_AWS_ACCOUNT_ID>"
$env:TAILSCALE_SECRET_NAME = "<YOUR_PROJECT>/tailscale-auth-key"
```

Create or update the Tailscale auth key secret:

```powershell
.\scripts\windows\New-ZtTailscaleSecret.ps1 `
  -SecretName $env:TAILSCALE_SECRET_NAME `
  -AuthKey "tskey-auth-REPLACE_ME"
```

The scripts do not print the secret value after creation.

## Backend State

Live deploys require `terraform\backend.hcl`. Create it from
`terraform\backend.hcl.example` with the POC S3 state bucket before deployment. The backend uses S3 lockfiles for locking.

## POC Flow

Run local validation:

```powershell
.\scripts\windows\Invoke-ZtStatic.ps1
.\scripts\windows\Invoke-ZtPolicy.ps1
```

Run preflight:

```powershell
.\scripts\windows\Test-ZtPreflight.ps1
```

Deploy:

```powershell
.\scripts\windows\Invoke-ZtDeploy.ps1
```

Verify live AWS posture:

```powershell
.\scripts\windows\Invoke-ZtLive.ps1
```

Fetch remote bootstrap and verification logs through SSM:

```powershell
.\scripts\windows\Get-ZtLogs.ps1
```

The files are written locally to:

```text
logs\zt-bootstrap.log
logs\zt-verify.json
```

Destroy when finished:

```powershell
.\scripts\windows\Remove-ZtDeployment.ps1 -ConfirmDestroy zt-infra-v2
```

## Windows nono Client Track

After the AWS backend verifies, test the native Windows `nono` client against
the private control path. Keep this separate from the backend deployment:

1. Confirm the Windows endpoint is joined to the same Tailscale tailnet as the
   EC2 instance:

```powershell
tailscale status
tailscale dns status
curl.exe <TAILSCALE_HTTPS_URL>
```

2. Confirm `nono` is installed and the Windows Filtering Platform service is
   running:

```powershell
nono --version
Get-Service -Name nono-wfp-service
```

The service may be displayed as `nono-wfp-service`; older notes may refer to
the same WFP enforcement component as `nono_wfp`.

3. Use a workspace under the current user's profile, not a root-owned or
   administrator-created directory:

```powershell
$ws = Join-Path $env:TEMP "nono-workspace"
New-Item -ItemType Directory -Force -Path $ws | Out-Null
Set-Location $ws
```

4. Confirm `nono` can launch a confined process:

```powershell
nono run --workspace $ws -- cmd.exe /d /c "echo NONO_OK"
"EXIT:$LASTEXITCODE"
```

Expected result: `NONO_OK` and `EXIT:0`.

5. Verify network policy reasoning for the private ZT-Infra Tailscale endpoint:

```powershell
$ztHost = "<TAILSCALE_DNS_NAME>"
nono why --host $ztHost --port 443 --block-net
nono why --host $ztHost --port 443
```

Expected results:

- With `--block-net`: `DENIED` with reason `network_blocked`.
- Without `--block-net`: `ALLOWED` with reason `network_allowed`.

6. Optionally verify process-level WFP blocking with a simple network client:

```powershell
nono run --workspace $ws --block-net -- C:\Windows\System32\ping.exe -n 1 1.1.1.1
"EXIT:$LASTEXITCODE"
```

This is environment-dependent because ICMP may already be blocked by the
network or by the Windows sandbox context. Treat `nono why` as the clean policy
evidence and runtime network clients as additional smoke tests.

Current Windows limitation: `nono v0.66.1` accepts `--allow-domain`, but
domain-specific proxy filtering is not implemented for Windows supervised
execution yet. The supported Windows proof today is broad outbound allowed vs.
`--block-net` denied policy reasoning. If `--allow-domain` reports that proxy
filtering is unsupported, that is expected fail-closed behavior.

The AWS POC remains responsible for private infrastructure, SSM fallback,
Tailscale Serve, KMS-signed audit records, CloudWatch evidence, and
`/var/log/zt-verify.json`. The Windows client POC is responsible for native
endpoint coordination and local WFP enforcement.
