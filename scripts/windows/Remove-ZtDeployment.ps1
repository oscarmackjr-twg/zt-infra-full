[CmdletBinding()]
param(
    [string] $AwsProfile = $env:AWS_PROFILE,
    [string] $AwsRegion = $(if ($env:AWS_REGION) { $env:AWS_REGION } else { "us-east-2" }),
    [string] $AllowedAwsAccountId = $env:TF_VAR_allowed_aws_account_id,
    [string] $ConfirmDestroy = $env:CONFIRM_DESTROY
)

. "$PSScriptRoot\ZtCommon.ps1"

Set-ZtAwsEnvironment -AwsProfile $AwsProfile -AwsRegion $AwsRegion -AllowedAwsAccountId $AllowedAwsAccountId

$terraformDir = Get-ZtTerraformDir
$backendConfig = Join-Path $terraformDir "backend.hcl"
if (-not (Test-Path $backendConfig)) {
    throw @"
Missing terraform/backend.hcl.

Create it from terraform/backend.hcl.example with this deployment's S3
state bucket and DynamoDB lock table before running destroy.
"@
}

if ($ConfirmDestroy -ne "zt-infra-v2") {
    throw @"
Refusing to destroy without explicit confirmation.

Run:
  .\scripts\windows\Remove-ZtDeployment.ps1 -ConfirmDestroy zt-infra-v2
"@
}

Push-Location $terraformDir
try {
    Invoke-ZtNative terraform "init" "-backend-config=backend.hcl"
    Invoke-ZtNative terraform "destroy" "-auto-approve"
}
finally {
    Pop-Location
}
