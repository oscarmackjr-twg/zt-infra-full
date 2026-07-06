[CmdletBinding()]
param(
    [string] $AwsProfile = $env:AWS_PROFILE,
    [string] $AwsRegion = $(if ($env:AWS_REGION) { $env:AWS_REGION } else { "us-east-2" }),
    [string] $InstanceId = $env:INSTANCE_ID,
    [int] $FetchLogLines = $(if ($env:FETCH_LOG_LINES) { [int] $env:FETCH_LOG_LINES } else { 160 }),
    [int] $SsmWaitAttempts = $(if ($env:SSM_WAIT_ATTEMPTS) { [int] $env:SSM_WAIT_ATTEMPTS } else { 40 }),
    [int] $SsmWaitSeconds = $(if ($env:SSM_WAIT_SECONDS) { [int] $env:SSM_WAIT_SECONDS } else { 5 }),
    [int] $VerifyWaitAttempts = $(if ($env:VERIFY_WAIT_ATTEMPTS) { [int] $env:VERIFY_WAIT_ATTEMPTS } else { 60 }),
    [int] $VerifyWaitSeconds = $(if ($env:VERIFY_WAIT_SECONDS) { [int] $env:VERIFY_WAIT_SECONDS } else { 5 })
)

. "$PSScriptRoot\ZtCommon.ps1"

Set-ZtAwsEnvironment -AwsProfile $AwsProfile -AwsRegion $AwsRegion
Require-ZtCommand "aws" "Install AWS CLI v2 for Windows and ensure aws.exe is on PATH."
Require-ZtCommand "terraform" "Install Terraform for Windows and ensure terraform.exe is on PATH."
Ensure-ZtDirectories

if ([string]::IsNullOrWhiteSpace($InstanceId)) {
    Push-Location (Get-ZtTerraformDir)
    try {
        $rawOutput = & terraform output -raw instance_id
        if ($LASTEXITCODE -ne 0) {
            throw "terraform output -raw instance_id failed with code $LASTEXITCODE"
        }
        $InstanceId = ($rawOutput -join "`n").Trim()
    }
    finally {
        Pop-Location
    }
}

if ([string]::IsNullOrWhiteSpace($InstanceId)) {
    throw "INSTANCE_ID is empty and terraform output did not return an instance ID."
}

function Wait-ZtSsmOnline {
    for ($n = 1; $n -le $SsmWaitAttempts; $n++) {
        $ssmArgs = @(
            "ssm", "describe-instance-information",
            "--profile", $env:AWS_PROFILE,
            "--region", $env:AWS_REGION,
            "--filters", "Key=InstanceIds,Values=$InstanceId",
            "--query", "InstanceInformationList[0].PingStatus",
            "--output", "text"
        )
        $oldEap = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        try {
            $output = & aws @ssmArgs 2>&1
        }
        finally {
            $ErrorActionPreference = $oldEap
        }
        if ($LASTEXITCODE -ne 0) {
            throw "aws ssm describe-instance-information failed with exit code ${LASTEXITCODE}: $output"
        }
        $stdout = $output | Where-Object { $_ -is [string] }
        $ping = ($stdout -join [Environment]::NewLine).Trim()
        if ($ping -eq "Online") {
            return
        }
        Write-Host "waiting for SSM on $InstanceId ($n/$SsmWaitAttempts; status=$ping)"
        Start-Sleep -Seconds $SsmWaitSeconds
    }
    throw "SSM did not become Online for $InstanceId"
}

function Invoke-ZtSsmShellCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Name,
        [Parameter(Mandatory = $true)]
        [string] $Command
    )

    $parametersPath = Join-Path ([System.IO.Path]::GetTempPath()) "zt-ssm-parameters-$([Guid]::NewGuid().ToString('N')).json"
    $parametersUri = "file://" + $parametersPath.Replace('\', '/')
    try {
        @{ commands = @($Command) } | ConvertTo-Json -Compress | Set-Content -Path $parametersPath -Encoding ascii
        $commandId = Invoke-ZtAwsText @(
            "ssm", "send-command",
            "--profile", $env:AWS_PROFILE,
            "--region", $env:AWS_REGION,
            "--instance-ids", $InstanceId,
            "--document-name", "AWS-RunShellScript",
            "--parameters", $parametersUri,
            "--query", "Command.CommandId",
            "--output", "text"
        )

        Invoke-ZtNative aws "ssm" "wait" "command-executed" `
            "--profile" $env:AWS_PROFILE `
            "--region" $env:AWS_REGION `
            "--command-id" $commandId `
            "--instance-id" $InstanceId

        $content = Invoke-ZtAwsText @(
            "ssm", "get-command-invocation",
            "--profile", $env:AWS_PROFILE,
            "--region", $env:AWS_REGION,
            "--command-id", $commandId,
            "--instance-id", $InstanceId,
            "--query", "StandardOutputContent",
            "--output", "text"
        )

        $outPath = Join-Path (Join-Path (Get-ZtRepoRoot) "logs") $Name
        $content | Tee-Object -FilePath $outPath
    }
    finally {
        Remove-Item -Force -ErrorAction SilentlyContinue $parametersPath
    }
}

Wait-ZtSsmOnline
Invoke-ZtSsmShellCommand -Name "zt-bootstrap.log" -Command "sudo tail -n $FetchLogLines /var/log/zt-bootstrap.log"
Invoke-ZtSsmShellCommand -Name "zt-verify.json" -Command "n=1; while test `$n -le $VerifyWaitAttempts; do if sudo test -s /var/log/zt-verify.json; then sudo cat /var/log/zt-verify.json; exit 0; fi; echo waiting for /var/log/zt-verify.json `$n/$VerifyWaitAttempts; sleep $VerifyWaitSeconds; n=`$((n + 1)); done; echo /var/log/zt-verify.json was not generated >&2; exit 1"
