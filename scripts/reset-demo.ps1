# SYNTHETIC-SALES-ASSIST-AUTHORED-M5
[CmdletBinding()]
param(
    [string]$PythonPath,
    [string]$DataDir,
    [ValidateRange(1024, 65535)][int]$Port = 8765,
    [switch]$ConfirmReset,
    [switch]$SeedDemo
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'lifecycle-common.ps1')

$operationLock = $null
$serviceMaintenanceLock = $null
try {
    if (-not $ConfirmReset) { throw 'RESET_CONFIRMATION_REQUIRED' }
    $pythonRuntime = Select-SsaPythonRuntime -PythonPath $PythonPath `
        -PythonPathWasBound ($PSBoundParameters.ContainsKey('PythonPath'))
    Write-SsaPythonRuntimeNotice -Runtime $pythonRuntime
    $python = [string]$pythonRuntime.Path
    $root = Resolve-SsaDataRoot -DataDir $DataDir
    $paths = Get-SsaRuntimePaths -DataRoot $root
    Initialize-SsaDirectories -Paths $paths
    $operationLock = Enter-SsaLifecycleOperationLock -LockPath $paths.LifecycleLock
    [void](Invoke-SsaCliJson -PythonPath $python -DataRoot $root `
        -CommandArguments @('doctor'))
    Assert-SsaControlledDirectory -Path $paths.Data
    Assert-SsaControlledDirectory -Path $paths.Backups
    Assert-SsaControlledDirectory -Path $paths.Runtime
    Assert-SsaRuntimeFileNotReparsePoint -Path $paths.Database

    $backupPath = $null
    if ([IO.File]::Exists($paths.Database)) {
        $stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')
        $backupPath = Join-Path $paths.Backups (
            'pre-reset-{0}-{1}.sqlite3' -f $stamp, [Guid]::NewGuid().ToString('N')
        )
        [void](Invoke-SsaCliJson -PythonPath $python -DataRoot $root `
            -CommandArguments @('db', 'backup', $backupPath, '--create-parent'))
    }

    $stopScript = Join-Path $PSScriptRoot 'stop.ps1'
    if ($pythonRuntime.Source -ceq 'SSA_PYTHON_DEVELOPMENT_NONPORTABLE') {
        $stopOutput = @(& $stopScript -DataDir $root 2>&1)
    }
    else {
        $stopOutput = @(& $stopScript -PythonPath $python -DataDir $root 2>&1)
    }
    if ($LASTEXITCODE -ne 0) { throw 'OWNED_STOP_FAILED' }
    $serviceMaintenanceLock = Enter-SsaLeaseCleanupLock -LockPath $paths.Lock
    if ([IO.File]::Exists($paths.Receipt)) { throw 'RUNTIME_RECEIPT_STILL_PRESENT' }

    $allowedRemovals = @(
        [string]$paths.Database
        ([string]$paths.Database + '-journal')
        ([string]$paths.Database + '-wal')
        ([string]$paths.Database + '-shm')
        [string]$paths.ActivityLock
    )
    foreach ($path in $allowedRemovals) {
        Assert-SsaControlledDirectory -Path $paths.Data
        Assert-SsaRuntimeFileNotReparsePoint -Path $path
        $resolved = [IO.Path]::GetFullPath($path)
        $dataPrefix = [IO.Path]::GetFullPath($paths.Data).TrimEnd(
            [IO.Path]::DirectorySeparatorChar
        ) + [IO.Path]::DirectorySeparatorChar
        if (-not $resolved.StartsWith($dataPrefix, [StringComparison]::OrdinalIgnoreCase)) {
            throw 'RESET_TARGET_SCOPE_INVALID'
        }
        if ([IO.File]::Exists($resolved)) {
            Remove-Item -LiteralPath $resolved -Force
        }
    }
    Assert-SsaControlledDirectory -Path $paths.Data
    $initialization = Invoke-SsaCliJson -PythonPath $python -DataRoot $root `
        -CommandArguments @('db', 'init')
    $verification = Invoke-SsaCliJson -PythonPath $python -DataRoot $root `
        -CommandArguments @('db', 'verify', '--deep')
    if ($verification.result.healthy -ne $true -or $verification.result.schema_version -ne 4) {
        throw 'RESET_VERIFICATION_FAILED'
    }
    if ($SeedDemo) {
        $installation = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
        $demoTool = Join-Path $installation 'tools\release_support.py'
        & $python -I $demoTool reseed --install-root $installation --data-dir $root
        if ($LASTEXITCODE -ne 0) { throw 'RESET_DEMO_SEED_FAILED' }
    }
    try { $serviceMaintenanceLock.Unlock(64, 1) } catch { }
    $serviceMaintenanceLock.Dispose()
    $serviceMaintenanceLock = $null
    Remove-SsaStaleLease -Paths $paths
    Exit-SsaLifecycleOperationLock -Stream $operationLock
    $operationLock = $null
    Write-SsaJsonResult -Value @{
        state = 'RESET'
        backup_path = $backupPath
        database_path = $paths.Database
        database_schema_version = 4
        data_dir = $root
        port = $Port
        verified = $true
    }
    exit 0
}
catch {
    if ($null -ne $serviceMaintenanceLock) {
        try { $serviceMaintenanceLock.Unlock(64, 1) } catch { }
        $serviceMaintenanceLock.Dispose()
        $serviceMaintenanceLock = $null
    }
    if ($null -ne $operationLock) {
        Exit-SsaLifecycleOperationLock -Stream $operationLock
        $operationLock = $null
    }
    Write-Error -ErrorId 'SSA_RESET_FAILED' -Message ([string]$_.Exception.Message)
    exit 1
}
