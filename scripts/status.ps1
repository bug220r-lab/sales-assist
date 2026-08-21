# SYNTHETIC-SALES-ASSIST-AUTHORED-M5
[CmdletBinding()]
param(
    [string]$PythonPath = 'python',
    [string]$DataDir
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'lifecycle-common.ps1')

try {
    $python = Resolve-SsaPythonPath -PythonPath $PythonPath
    $root = Resolve-SsaDataRoot -DataDir $DataDir
    $paths = Get-SsaRuntimePaths -DataRoot $root
    $doctor = $null
    try {
        $doctor = Invoke-SsaCliJson -PythonPath $python -DataRoot $root `
            -CommandArguments @('doctor')
    }
    catch { $doctor = $null }
    $safetyCounters = if ($null -ne $doctor) {
        $doctor.result.safety_counters
    } else {
        Get-SsaUnavailableSafetyCounters
    }
    $installedAppVersion = if ($null -ne $doctor) {
        [string]$doctor.result.app_version
    } else { $script:SsaAppVersion }
    $stoppedSchemaVersion = if ($null -ne $doctor) {
        $doctor.result.schema_version
    } else { $null }
    if (Test-Path -LiteralPath $paths.Data) {
        Assert-SsaControlledDirectory -Path $paths.Data
    }
    if (Test-Path -LiteralPath $paths.Runtime) {
        Assert-SsaControlledDirectory -Path $paths.Runtime
    }
    $databaseSize = if ([IO.File]::Exists($paths.Database)) {
        (Get-Item -LiteralPath $paths.Database).Length
    } else { 0 }
    if (-not [IO.File]::Exists($paths.Receipt)) {
        if ([IO.File]::Exists($paths.Lock)) {
            $leaseProbe = Enter-SsaLeaseCleanupLock -LockPath $paths.Lock
            try { $leaseProbe.Unlock(64, 1) } catch { }
            $leaseProbe.Dispose()
        }
        Write-SsaJsonResult -Value @{
            state = 'STOPPED'
            app_version = $installedAppVersion
            build_version = $script:SsaBuildVersion
            data_dir = $root
            database_path = $paths.Database
            database_schema_version = $stoppedSchemaVersion
            database_size_bytes = $databaseSize
            last_health_status = 'NOT_RUNNING'
            origin = $null
            pid = $null
            port = $null
            safety_counters = $safetyCounters
        }
        exit 0
    }

    $receipt = Read-SsaRuntimeReceipt -ReceiptPath $paths.Receipt -ExpectedDataRoot $root
    $owned = Get-SsaOwnedProcess -Receipt $receipt -PythonPath $python -DataRoot $root `
        -ReceiptPath $paths.Receipt -LockPath $paths.Lock
    if ($null -eq $owned) {
        Write-SsaJsonResult -Value @{
            state = 'STALE'
            app_version = [string]$receipt.app_version
            build_version = [string]$receipt.build_version
            data_dir = $root
            database_path = $paths.Database
            database_schema_version = [int]$receipt.database_schema_version
            database_size_bytes = $databaseSize
            last_health_status = 'NOT_RUNNING'
            origin = [string]$receipt.origin
            pid = [int]$receipt.pid
            port = [int]$receipt.port
            safety_counters = $safetyCounters
        }
        exit 0
    }
    $lastHealth = Get-SsaLastHealthStatus -Receipt $receipt
    Write-SsaJsonResult -Value @{
        state = 'RUNNING'
        app_version = [string]$receipt.app_version
        build_version = [string]$receipt.build_version
        database_path = [string]$receipt.database_path
        database_schema_version = [int]$receipt.database_schema_version
        database_size_bytes = $databaseSize
        data_dir = $root
        last_health_status = $lastHealth
        origin = [string]$receipt.origin
        pid = [int]$receipt.pid
        port = [int]$receipt.port
        safety_counters = $safetyCounters
    }
    exit 0
}
catch {
    Write-Error -ErrorId 'SSA_STATUS_FAILED' -Message ([string]$_.Exception.Message)
    exit 1
}
