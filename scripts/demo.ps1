# SYNTHETIC-SALES-ASSIST-AUTHORED-M8
[CmdletBinding()]
param(
    [ValidateSet('Start', 'Stop', 'Status', 'Backup', 'Reset', 'Upgrade', 'Remove')]
    [string]$Action = 'Start',
    [string]$DataDir,
    [ValidateRange(1024, 65535)][int]$Port = 8765,
    [switch]$NoBrowser,
    [switch]$DevelopmentRuntime,
    [switch]$Confirmed
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'lifecycle-common.ps1')
$installation = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$oldPythonPath = $env:PYTHONPATH
$oldSsaPython = $env:SSA_PYTHON
try {
    $metadataPath = Join-Path $installation 'release-build.json'
    Assert-SsaRuntimeFileNotReparsePoint -Path $metadataPath
    $metadata = Get-Content -LiteralPath $metadataPath -Raw | ConvertFrom-Json
    if ($metadata.schema -cne 'synthetic-sales-assist-release-build/v1' -or
        $metadata.release_id -cnotmatch '^demo-[0-9]+\.[0-9]+\.[0-9]+-[0-9a-f]{12}$') {
        throw 'RELEASE_METADATA_INVALID'
    }
    $env:PYTHONPATH = Join-Path $installation 'src'
    if ($DevelopmentRuntime -and [string]::IsNullOrWhiteSpace($env:SSA_PYTHON)) {
        $env:SSA_PYTHON = Get-SsaVerifiedCodexPythonPath
    }
    $runtime = Select-SsaPythonRuntime -PythonPath '' -PythonPathWasBound $false
    Write-SsaPythonRuntimeNotice -Runtime $runtime
    $python = [string]$runtime.Path
    $support = Join-Path $installation 'tools\release_support.py'
    if ($Action -ne 'Remove') {
        & $python -I $support verify --install-root $installation
        if ($LASTEXITCODE -ne 0) { throw 'RELEASE_PAYLOAD_VERIFICATION_FAILED' }
    }
    if ($Action -eq 'Upgrade' -and [string]::IsNullOrWhiteSpace($DataDir)) {
        $DataDir = Read-Host 'Absolute path of the disposable demo data root to upgrade'
    }
    if ([string]::IsNullOrWhiteSpace($DataDir)) {
        $dataRootJson = & $python -I $support data-root --install-root $installation
        if ($LASTEXITCODE -ne 0) { throw 'DEMO_DATA_ROOT_UNAVAILABLE' }
        $DataDir = ($dataRootJson | ConvertFrom-Json).data_dir
    }
    $dataRoot = Resolve-SsaDataRoot -DataDir $DataDir
    switch ($Action) {
        'Start' {
            & (Join-Path $PSScriptRoot 'start.ps1') -DataDir $dataRoot -Port $Port `
                -NoBrowser -PrepareDemo
            if ($LASTEXITCODE -ne 0) { throw 'DEMO_START_FAILED' }
            & $python -I $support configure --install-root $installation --data-dir $dataRoot
            if ($LASTEXITCODE -ne 0) {
                & (Join-Path $PSScriptRoot 'stop.ps1') -DataDir $dataRoot
                throw 'DEMO_DATA_ROOT_CONFIGURATION_FAILED'
            }
            if (-not $NoBrowser) { Start-Process "http://127.0.0.1:$Port/overview" }
        }
        'Upgrade' {
            # start.ps1 holds the lifecycle lock through verified backup, preparation,
            # startup and ownership checks. An active service fails before preparation.
            & (Join-Path $PSScriptRoot 'start.ps1') -DataDir $dataRoot -NoBrowser `
                -Port $Port -PrepareDemo -AllowSchema4Upgrade
            if ($LASTEXITCODE -ne 0) { throw 'DEMO_UPGRADE_FAILED_STOP_OWNED_SERVICE_FIRST' }
            & $python -I $support configure --install-root $installation --data-dir $dataRoot
            if ($LASTEXITCODE -ne 0) {
                & (Join-Path $PSScriptRoot 'stop.ps1') -DataDir $dataRoot
                throw 'DEMO_DATA_ROOT_CONFIGURATION_FAILED'
            }
        }
        'Stop' { & (Join-Path $PSScriptRoot 'stop.ps1') -DataDir $dataRoot }
        'Status' { & (Join-Path $PSScriptRoot 'status.ps1') -DataDir $dataRoot }
        'Backup' {
            $paths = Get-SsaRuntimePaths -DataRoot $dataRoot
            $name = 'demo-backup-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffffff')
            $destination = Join-Path $paths.Backups ($name + '.sqlite3')
            $receipt = Invoke-SsaCliJson -PythonPath $python -DataRoot $dataRoot `
                -CommandArguments @('db', 'backup', $destination, '--create-parent')
            $receipt | ConvertTo-Json -Depth 64 -Compress
        }
        'Reset' {
            if (-not $Confirmed) {
                $answer = Read-Host ('Reset only this disposable data root after backup: ' +
                    $dataRoot + ' ? Type RESET')
                if ($answer -cne 'RESET') { throw 'RESET_CANCELLED' }
            }
            & (Join-Path $PSScriptRoot 'reset-demo.ps1') -DataDir $dataRoot -ConfirmReset -SeedDemo
            if ($LASTEXITCODE -ne 0) { throw 'DEMO_RESET_FAILED' }
        }
        'Remove' {
            if (-not $Confirmed) {
                $answer = Read-Host ('Remove unchanged package files from ' + $installation +
                    ' while preserving data/backups and modified files? Type REMOVE')
                if ($answer -cne 'REMOVE') { throw 'REMOVE_CANCELLED' }
            }
            $paths = Get-SsaRuntimePaths -DataRoot $dataRoot
            Initialize-SsaDirectories -Paths $paths
            $removalLock = Enter-SsaLifecycleOperationLock -LockPath $paths.LifecycleLock
            $removalLease = $null
            try {
                & (Join-Path $PSScriptRoot 'stop.ps1') -DataDir $dataRoot
                if ($LASTEXITCODE -ne 0) { throw 'OWNED_STOP_REQUIRED_BEFORE_REMOVE' }
                $removalLease = Enter-SsaLeaseCleanupLock -LockPath $paths.Lock
                & $python -I $support remove --install-root $installation --confirm-remove
            }
            finally {
                if ($null -ne $removalLease) {
                    try { $removalLease.Unlock(64, 1) } catch { }
                    $removalLease.Dispose()
                }
                Exit-SsaLifecycleOperationLock -Stream $removalLock
            }
        }
    }
    if ($LASTEXITCODE -ne 0) { throw 'DEMO_OPERATION_FAILED' }
    exit 0
}
catch {
    Write-Host ('Synthetic demo could not complete: ' + $_.Exception.Message)
    Write-Host 'Requires local CPython 3.12 with tzdata 2026.3 and an intact extracted package.'
    Write-Host 'The Codex runtime option is DEVELOPMENT/NONPORTABLE. No runtime is downloaded.'
    exit 1
}
finally {
    $env:PYTHONPATH = $oldPythonPath
    $env:SSA_PYTHON = $oldSsaPython
}
