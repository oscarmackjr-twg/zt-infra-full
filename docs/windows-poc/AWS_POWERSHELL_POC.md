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
`terraform\backend.hcl.example` with the POC S3 state bucket and DynamoDB lock
table before deployment.

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

1. Confirm the Windows endpoint has Tailscale connectivity to the private
   control surface.
2. Confirm `nono` is installed and healthy.
3. Confirm the `nono_wfp` service is installed and running.
4. Submit a deny/allow action through the same `/actions` contract.
5. Confirm `nono_wfp` applies the expected local Windows Filtering Platform
   enforcement.

The AWS POC remains responsible for private infrastructure, SSM fallback,
Tailscale Serve, KMS-signed audit records, CloudWatch evidence, and
`/var/log/zt-verify.json`. The Windows client POC is responsible for native
endpoint coordination and local WFP enforcement.
