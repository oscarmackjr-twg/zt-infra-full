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

Push-Location $terraformDir
try {
    Invoke-ZtNative terraform "fmt" "-recursive"
    if (Test-Path "backend.hcl") {
        Invoke-ZtNative terraform "init" "-backend-config=backend.hcl"
    }
    else {
        Invoke-ZtNative terraform "init" "-backend=false"
    }
    Invoke-ZtNative terraform "validate"
}
finally {
    Pop-Location
}

Push-Location $repoRoot
try {
    Invoke-ZtNative $python "-m" "pytest" "zt-verify/tests"
    Invoke-ZtNative $python "-m" "pytest" `
        "tests/test_static_repo.py" `
        "tests/test_bootstrap_simulation.py" `
        "tests/test_langgraph_plugin.py" `
        "tests/test_openai_assistants_wrapper.py" `
        "tests/test_openai_responses_wrapper.py" `
        "tests/test_openai_agents_sdk_guardrail.py" `
        "tests/test_mcp_zero_trust_gateway.py" `
        "tests/test_a2a_policy_proxy.py" `
        "tests/test_interoperability_demo_contract.py" `
        "tests/test_caf_roadmap.py"

    if (Get-Command "go" -ErrorAction SilentlyContinue) {
        Push-Location (Join-Path $repoRoot "test-vectors\canonical-form\skeletons\go")
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
        Write-Warning "go is not installed; skipping CAF Go skeleton tests."
    }

    if (Get-Command "cargo" -ErrorAction SilentlyContinue) {
        Push-Location (Join-Path $repoRoot "test-vectors\canonical-form\skeletons\rust")
        try {
            Invoke-ZtNative cargo "test"
        }
        finally {
            Pop-Location
        }
    }
    else {
        Write-Warning "cargo is not installed; skipping CAF Rust skeleton tests."
    }
}
finally {
    Pop-Location
}
