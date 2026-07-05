[CmdletBinding()]
param(
    [string] $SecretName = $env:TAILSCALE_SECRET_NAME,
    [Parameter(Mandatory = $true)]
    [string] $AuthKey,
    [string] $AwsProfile = $env:AWS_PROFILE,
    [string] $AwsRegion = $(if ($env:AWS_REGION) { $env:AWS_REGION } else { "us-east-2" })
)

. "$PSScriptRoot\ZtCommon.ps1"

Set-ZtAwsEnvironment -AwsProfile $AwsProfile -AwsRegion $AwsRegion -TailscaleSecretName $SecretName
Require-ZtCommand "aws" "Install AWS CLI v2 for Windows."
$SecretName = Require-ZtEnv "TAILSCALE_SECRET_NAME" "Example: `$env:TAILSCALE_SECRET_NAME = 'zt-infra/tailscale-auth-key'"
Assert-ZtSecretName $SecretName
Assert-ZtTailscaleAuthKey $AuthKey

$exists = $true
& aws secretsmanager describe-secret --secret-id $SecretName --profile $env:AWS_PROFILE --region $env:AWS_REGION *> $null
if ($LASTEXITCODE -ne 0) {
    $exists = $false
}

if ($exists) {
    Invoke-ZtNative aws "secretsmanager" "put-secret-value" "--secret-id" $SecretName "--secret-string" $AuthKey "--profile" $env:AWS_PROFILE "--region" $env:AWS_REGION | Out-Null
    Write-Host "updated secret: $SecretName"
}
else {
    Invoke-ZtNative aws "secretsmanager" "create-secret" "--name" $SecretName "--secret-string" $AuthKey "--profile" $env:AWS_PROFILE "--region" $env:AWS_REGION | Out-Null
    Write-Host "created secret: $SecretName"
}
