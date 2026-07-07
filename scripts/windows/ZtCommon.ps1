Set-StrictMode -Version 3.0
$ErrorActionPreference = "Stop"

function Get-ZtRepoRoot {
    $scriptDir = Split-Path -Parent $PSScriptRoot
    return Split-Path -Parent $scriptDir
}

function Get-ZtTerraformDir {
    return Join-Path (Get-ZtRepoRoot) "terraform"
}

function Resolve-ZtPython {
    $repoRoot = Get-ZtRepoRoot
    $venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        return $venvPython
    }
    return "python"
}

function Require-ZtCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Name,
        [string] $InstallHint = ""
    )

    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        if ($InstallHint) {
            throw "$Name missing. $InstallHint"
        }
        throw "$Name missing."
    }
}

function Require-ZtEnv {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Name,
        [string] $Message = ""
    )

    $value = [Environment]::GetEnvironmentVariable($Name, "Process")
    if ([string]::IsNullOrWhiteSpace($value)) {
        if ($Message) {
            throw "Set $Name. $Message"
        }
        throw "Set $Name."
    }
    return $value
}

function Set-ZtAwsEnvironment {
    param(
        [string] $AwsProfile = $env:AWS_PROFILE,
        [string] $AwsRegion = $(if ($env:AWS_REGION) { $env:AWS_REGION } else { "us-east-2" }),
        [string] $AllowedAwsAccountId = $env:TF_VAR_allowed_aws_account_id,
        [string] $ProjectName = $(if ($env:PROJECT_NAME) { $env:PROJECT_NAME } else { "zt-infra-v2" }),
        [string] $TailscaleSecretName = $env:TAILSCALE_SECRET_NAME
    )

    if ([string]::IsNullOrWhiteSpace($AwsProfile)) {
        throw "Set AWS_PROFILE to the AWS CLI profile for this POC."
    }

    $env:AWS_PROFILE = $AwsProfile
    $env:AWS_REGION = $AwsRegion
    $env:PROJECT_NAME = $ProjectName
    if (-not [string]::IsNullOrWhiteSpace($TailscaleSecretName)) {
        $env:TAILSCALE_SECRET_NAME = $TailscaleSecretName
    }
    if (-not [string]::IsNullOrWhiteSpace($AllowedAwsAccountId)) {
        $env:TF_VAR_allowed_aws_account_id = $AllowedAwsAccountId
    }

    $env:TF_VAR_aws_profile = $env:AWS_PROFILE
    $env:TF_VAR_aws_region = $env:AWS_REGION
    $env:TF_VAR_project_name = $env:PROJECT_NAME
    if ($env:TAILSCALE_SECRET_NAME) {
        $env:TF_VAR_tailscale_secret_name = $env:TAILSCALE_SECRET_NAME
    }
}

function Assert-ZtTailscaleAuthKey {
    param(
        [Parameter(Mandatory = $true)]
        [string] $AuthKey
    )

    if ($AuthKey -notmatch '^tskey-auth-[A-Za-z0-9]+-[A-Za-z0-9]+$') {
        throw "Tailscale auth key format is invalid; expected tskey-auth-...-... without surrounding whitespace."
    }
}

function Assert-ZtSecretName {
    param(
        [Parameter(Mandatory = $true)]
        [string] $SecretName
    )

    if ($SecretName -notmatch '^[A-Za-z0-9/_+=.@-]+$') {
        throw "Secret name must contain only AWS Secrets Manager-safe path characters."
    }
}

function Invoke-ZtNative {
    param(
        [Parameter(Mandatory = $true)]
        [string] $FilePath,
        [Parameter(ValueFromRemainingArguments = $true)]
        [string[]] $Arguments
    )

    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$FilePath exited with code $LASTEXITCODE"
    }
}

function Invoke-ZtAwsText {
    param(
        [Parameter(Mandatory = $true)]
        [string[]] $Arguments
    )

    $output = & aws @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "aws $($Arguments -join ' ') exited with code $LASTEXITCODE"
    }
    return ($output -join "`n").Trim()
}

function Get-ZtTerraformOutput {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Name
    )

    Push-Location (Get-ZtTerraformDir)
    try {
        $output = & terraform output -raw $Name
        if ($LASTEXITCODE -ne 0) {
            throw "terraform output -raw $Name failed with code $LASTEXITCODE"
        }
        return ($output -join "`n").Trim()
    }
    finally {
        Pop-Location
    }
}

function Ensure-ZtDirectories {
    $repoRoot = Get-ZtRepoRoot
    New-Item -ItemType Directory -Force -Path (Join-Path $repoRoot "out") | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $repoRoot "logs") | Out-Null
}
