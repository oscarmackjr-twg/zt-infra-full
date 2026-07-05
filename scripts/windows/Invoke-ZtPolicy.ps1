[CmdletBinding()]
param()

. "$PSScriptRoot\ZtCommon.ps1"

$repoRoot = Get-ZtRepoRoot
$terraformDir = Get-ZtTerraformDir
$missing = $false

Push-Location $repoRoot
try {
    if (Get-Command "checkov" -ErrorAction SilentlyContinue) {
        Invoke-ZtNative checkov "-d" $terraformDir "--config-file" (Join-Path $repoRoot ".checkov.yml")
    }
    else {
        Write-Warning "checkov is not installed; skipping. Install it to enforce local policy checks."
        $missing = $true
    }

    if (Get-Command "tfsec" -ErrorAction SilentlyContinue) {
        Invoke-ZtNative tfsec $terraformDir "--config-file" (Join-Path $repoRoot ".tfsec.yml")
    }
    else {
        Write-Warning "tfsec is not installed; skipping. Install it to enforce local policy checks."
        $missing = $true
    }
}
finally {
    Pop-Location
}

if ($missing) {
    Write-Warning "Policy scan completed with missing local tools. GitHub Actions still runs policy checks in CI."
}
