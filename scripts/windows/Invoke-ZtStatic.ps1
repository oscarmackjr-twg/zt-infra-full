[CmdletBinding()]
param(
    [string] $AwsProfile = $env:AWS_PROFILE,
    [string] $AwsRegion = $(if ($env:AWS_REGION) { $env:AWS_REGION } else { "us-east-2" }),
    [string] $AllowedAwsAccountId = $env:TF_VAR_allowed_aws_account_id
)

. "$PSScriptRoot\ZtCommon.ps1"

Set-ZtAwsEnvironment -AwsProfile $AwsProfile -AwsRegion $AwsRegion -AllowedAwsAccountId $AllowedAwsAccountId
Require-ZtCommand "terraform" "Install Terraform for Windows and ensure terraform.exe is on PATH."
Require-ZtCommand "python" "Install Python 3.12+ for Windows and ensure python.exe is on PATH."

$repoRoot = Get-ZtRepoRoot
$terraformDir = Get-ZtTerraformDir
$python = Resolve-ZtPython
$pytestTempDir = Join-Path $repoRoot "tmp\pytest"
New-Item -ItemType Directory -Force -Path $pytestTempDir | Out-Null
$env:TMP = $pytestTempDir
$env:TEMP = $pytestTempDir
$env:PYTHONUTF8 = "1"
$gitBin = "C:\Program Files\Git\bin"
$gitUsrBin = "C:\Program Files\Git\usr\bin"
if ((Test-Path -LiteralPath $gitBin) -and (Test-Path -LiteralPath $gitUsrBin)) {
    $env:PATH = "$gitBin;$gitUsrBin;$env:PATH"
    $env:BASH_EXE = Join-Path $gitBin "bash.exe"
}

Push-Location $terraformDir
try {
    Invoke-ZtNative terraform "fmt" "-recursive"
    Invoke-ZtNative terraform "init" "-reconfigure" "-backend=false"
    Invoke-ZtNative terraform "validate"
}
finally {
    Pop-Location
}

Push-Location $repoRoot
try {
    Invoke-ZtNative $python "-m" "pytest" `
        "tests/test_static_repo.py" `
        "tests/test_bootstrap_simulation.py" `
        "tests/test_langgraph_plugin.py" `
        "tests/test_openai_assistants_wrapper.py" `
        "tests/test_openai_responses_wrapper.py" `
        "tests/test_openai_agents_sdk_guardrail.py" `
        "tests/test_mcp_zero_trust_gateway.py" `
        "tests/test_a2a_policy_proxy.py" `
        "tests/test_interoperability_demo_contract.py"

    $goSkeletonDir = Join-Path $repoRoot "test-vectors\canonical-form\skeletons\go"
    if ((Get-Command "go" -ErrorAction SilentlyContinue) -and (Test-Path -LiteralPath $goSkeletonDir)) {
        Push-Location $goSkeletonDir
        try {
            if (-not $env:GOCACHE) {
                $env:GOCACHE = Join-Path $env:TEMP "zt-infra-v2-go-cache"
            }
            Invoke-ZtNative go "test" "./..."
        }
        finally {
            Pop-Location
        }
    }
    else {
        Write-Warning "go or CAF Go skeleton directory is not available; skipping CAF Go skeleton tests."
    }

    $rustSkeletonDir = Join-Path $repoRoot "test-vectors\canonical-form\skeletons\rust"
    if ((Get-Command "cargo" -ErrorAction SilentlyContinue) -and (Test-Path -LiteralPath $rustSkeletonDir)) {
        Push-Location $rustSkeletonDir
        try {
            Invoke-ZtNative cargo "test"
        }
        finally {
            Pop-Location
        }
    }
    else {
        Write-Warning "cargo or CAF Rust skeleton directory is not available; skipping CAF Rust skeleton tests."
    }
}
finally {
    Pop-Location
}
