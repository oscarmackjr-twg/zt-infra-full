[CmdletBinding()]
param(
    [string] $AwsProfile = $env:AWS_PROFILE,
    [string] $AwsRegion = $(if ($env:AWS_REGION) { $env:AWS_REGION } else { "us-east-2" }),
    [string] $AllowedAwsAccountId = $env:TF_VAR_allowed_aws_account_id
)

. "$PSScriptRoot\ZtCommon.ps1"

Set-ZtAwsEnvironment -AwsProfile $AwsProfile -AwsRegion $AwsRegion -AllowedAwsAccountId $AllowedAwsAccountId
Require-ZtCommand "python" "Install Python 3.12+ for Windows and ensure python.exe is on PATH."

$repoRoot = Get-ZtRepoRoot
$python = Resolve-ZtPython

Push-Location $repoRoot
try {
    Invoke-ZtNative $python "-m" "pytest" "tests/test_live_integration.py"
}
finally {
    Pop-Location
}
