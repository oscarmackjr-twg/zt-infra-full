[CmdletBinding()]
param(
    [string] $AwsProfile = $env:AWS_PROFILE,
    [string] $AwsRegion = $(if ($env:AWS_REGION) { $env:AWS_REGION } else { "us-east-2" }),
    [string] $AllowedAwsAccountId = $env:TF_VAR_allowed_aws_account_id,
    [string] $TailscaleSecretName = $env:TAILSCALE_SECRET_NAME,
    [switch] $SkipPreflight
)

. "$PSScriptRoot\ZtCommon.ps1"

Set-ZtAwsEnvironment `
    -AwsProfile $AwsProfile `
    -AwsRegion $AwsRegion `
    -AllowedAwsAccountId $AllowedAwsAccountId `
    -TailscaleSecretName $TailscaleSecretName

if (-not $SkipPreflight) {
    & "$PSScriptRoot\Test-ZtPreflight.ps1" `
        -AwsProfile $env:AWS_PROFILE `
        -AwsRegion $env:AWS_REGION `
        -AllowedAwsAccountId $env:TF_VAR_allowed_aws_account_id `
        -TailscaleSecretName $env:TAILSCALE_SECRET_NAME
    if (-not $?) {
        throw "preflight failed"
    }
}

$terraformDir = Get-ZtTerraformDir
$backendConfig = Join-Path $terraformDir "backend.hcl"
if (-not (Test-Path $backendConfig)) {
    throw @"
Missing terraform/backend.hcl.

Create it from terraform/backend.hcl.example with this deployment's S3
state bucket before running live deploys. The backend uses S3 lockfiles for locking.
"@
}

Push-Location $terraformDir
try {
    Invoke-ZtNative terraform "init" "-reconfigure" "-backend-config=backend.hcl"
    Invoke-ZtNative terraform "apply" "-auto-approve"
    Invoke-ZtNative terraform "output"
}
finally {
    Pop-Location
}
