[CmdletBinding()]
param(
    [string] $AwsProfile = $env:AWS_PROFILE,
    [string] $AwsRegion = $(if ($env:AWS_REGION) { $env:AWS_REGION } else { "us-east-2" }),
    [string] $AllowedAwsAccountId = $env:TF_VAR_allowed_aws_account_id,
    [string] $TailscaleSecretName = $env:TAILSCALE_SECRET_NAME
)

. "$PSScriptRoot\ZtCommon.ps1"

Set-ZtAwsEnvironment `
    -AwsProfile $AwsProfile `
    -AwsRegion $AwsRegion `
    -AllowedAwsAccountId $AllowedAwsAccountId `
    -TailscaleSecretName $TailscaleSecretName

Require-ZtCommand "terraform" "Install Terraform for Windows and ensure terraform.exe is on PATH."
Require-ZtCommand "aws" "Install AWS CLI v2 for Windows and run aws configure sso or aws configure."
Require-ZtCommand "python" "Install Python 3.12+ for Windows and ensure python.exe is on PATH."
Require-ZtCommand "node" "Install Node.js 20+ for Windows and ensure node.exe is on PATH."

$secretName = Require-ZtEnv "TAILSCALE_SECRET_NAME" "Example: `$env:TAILSCALE_SECRET_NAME = 'zt-infra/tailscale-auth-key'"
Assert-ZtSecretName $secretName

Invoke-ZtNative aws "sts" "get-caller-identity" "--profile" $env:AWS_PROFILE "--region" $env:AWS_REGION | Out-Null

$secretExists = $true
$oldEap = $ErrorActionPreference
$ErrorActionPreference = "Continue"
try {
    $errorOutput = & aws secretsmanager describe-secret --secret-id $secretName --profile $env:AWS_PROFILE --region $env:AWS_REGION 2>&1
}
finally {
    $ErrorActionPreference = $oldEap
}
if ($LASTEXITCODE -ne 0) {
    $errorString = ($errorOutput -join [Environment]::NewLine)
    if ($errorString -match "ResourceNotFoundException") {
        $secretExists = $false
    }
    else {
        throw "aws secretsmanager describe-secret failed with exit code ${LASTEXITCODE}: $errorString"
    }
}

if ($secretExists) {
    $currentSecret = Invoke-ZtAwsText @(
        "secretsmanager", "get-secret-value",
        "--secret-id", $secretName,
        "--query", "SecretString",
        "--output", "text",
        "--profile", $env:AWS_PROFILE,
        "--region", $env:AWS_REGION
    )
    Assert-ZtTailscaleAuthKey $currentSecret
}
else {
    $authKey = $env:TAILSCALE_AUTH_KEY
    $repoKeyPath = Join-Path (Get-ZtRepoRoot) "tailscale-auth-key"
    if ([string]::IsNullOrWhiteSpace($authKey) -and (Test-Path $repoKeyPath)) {
        $authKey = (Get-Content -Raw -Path $repoKeyPath).Trim()
    }

    if ([string]::IsNullOrWhiteSpace($authKey)) {
        throw @"
Missing AWS Secrets Manager secret: $secretName

Create it without printing the key in logs:
  .\scripts\windows\New-ZtTailscaleSecret.ps1 -SecretName "$secretName" -AuthKey "tskey-auth-REPLACE_ME"

Or set `$env:TAILSCALE_AUTH_KEY for this process and rerun preflight.
"@
    }

    Assert-ZtTailscaleAuthKey $authKey
    Invoke-ZtNative aws "secretsmanager" "create-secret" "--name" $secretName "--secret-string" $authKey "--profile" $env:AWS_PROFILE "--region" $env:AWS_REGION | Out-Null
    Write-Host "created Tailscale auth key secret: $secretName"
}

Ensure-ZtDirectories
Write-Host "preflight ok: profile=$env:AWS_PROFILE region=$env:AWS_REGION"
