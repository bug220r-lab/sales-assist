# SYNTHETIC-SALES-ASSIST-AUTHORED-M5
[CmdletBinding()]
param(
    [string]$PythonPath,
    [string]$DataDir,
    [ValidateRange(1024, 65535)][int]$Port = 8765,
    [switch]$NoBrowser,
    [switch]$PrepareDemo,
    [switch]$AllowSchema4Upgrade,
    [ValidateRange(2, 60)][int]$StartupTimeoutSeconds = 20
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'lifecycle-common.ps1')

$child = $null
$childWasLaunched = $false
$operationLock = $null
$paths = $null
try {
    $pythonRuntime = Select-SsaPythonRuntime -PythonPath $PythonPath `
        -PythonPathWasBound ($PSBoundParameters.ContainsKey('PythonPath'))
    Write-SsaPythonRuntimeNotice -Runtime $pythonRuntime
    $python = [string]$pythonRuntime.Path
    $pythonOwnershipPaths = [string[]]$pythonRuntime.OwnershipPaths
    $root = Resolve-SsaDataRoot -DataDir $DataDir
    $paths = Get-SsaRuntimePaths -DataRoot $root
    Initialize-SsaDirectories -Paths $paths
    $operationLock = Enter-SsaLifecycleOperationLock -LockPath $paths.LifecycleLock
    [void](Invoke-SsaCliJson -PythonPath $python -DataRoot $root `
        -CommandArguments @('doctor'))

    $prior = Read-SsaRuntimeReceipt -ReceiptPath $paths.Receipt -ExpectedDataRoot $root
    if ($null -ne $prior) {
        $owned = Get-SsaOwnedProcess -Receipt $prior -PythonPath $pythonOwnershipPaths `
            -DataRoot $root `
            -ReceiptPath $paths.Receipt -LockPath $paths.Lock
        if ($null -ne $owned) { throw 'SERVICE_ALREADY_RUNNING' }
        Remove-SsaStaleLease -Paths $paths
    }
    elseif ([IO.File]::Exists($paths.Lock)) {
        Remove-SsaStaleLease -Paths $paths
    }

    if ($AllowSchema4Upgrade -and -not $PrepareDemo) {
        throw 'UPGRADE_REQUIRES_DEMO_PREPARATION'
    }
    if ($PrepareDemo) {
        $installation = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
        $support = Join-Path $installation 'tools\release_support.py'
        $prepareArguments = @($support, 'prepare', '--install-root', $installation,
            '--data-dir', $root)
        if ($AllowSchema4Upgrade) { $prepareArguments += '--allow-schema4-upgrade' }
        $preparationLease = Enter-SsaLeaseCleanupLock -LockPath $paths.Lock
        try {
            & $python -I @prepareArguments
            if ($LASTEXITCODE -ne 0) { throw 'DEMO_PREPARATION_FAILED' }
        }
        finally {
            try { $preparationLease.Unlock(64, 1) } catch { }
            $preparationLease.Dispose()
        }
        Remove-SsaStaleLease -Paths $paths
    }

    $argumentLine = @(
        '-s -E -m synthetic_sales_assist.portal',
        '--data-dir ' + (ConvertTo-SsaQuotedProcessArgument $root),
        '--host 127.0.0.1',
        '--port ' + $Port,
        '--runtime-receipt ' + (ConvertTo-SsaQuotedProcessArgument $paths.Receipt)
    ) -join ' '
    $repository = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\src'))
    $child = Start-Process -FilePath $python -ArgumentList $argumentLine -PassThru `
        -WindowStyle Hidden -WorkingDirectory $repository
    $childWasLaunched = $true

    $deadline = [DateTime]::UtcNow.AddSeconds($StartupTimeoutSeconds)
    $receipt = $null
    $health = $null
    while ([DateTime]::UtcNow -lt $deadline) {
        $child.Refresh()
        if ($child.HasExited) { throw 'SERVICE_START_FAILED' }
        if ([IO.File]::Exists($paths.Receipt)) {
            try {
                $receipt = Read-SsaRuntimeReceipt -ReceiptPath $paths.Receipt `
                    -ExpectedDataRoot $root
                $health = Invoke-SsaHealth -Receipt $receipt
                break
            }
            catch {
                $receipt = $null
                $health = $null
            }
        }
        Start-Sleep -Milliseconds 200
    }
    if ($null -eq $receipt -or $null -eq $health) { throw 'SERVICE_HEALTH_TIMEOUT' }
    $owned = Get-SsaOwnedProcess -Receipt $receipt -PythonPath $pythonOwnershipPaths `
        -DataRoot $root `
        -ReceiptPath $paths.Receipt -LockPath $paths.Lock
    if ($null -eq $owned -or $owned.Id -ne $child.Id) { throw 'PROCESS_OWNERSHIP_MISMATCH' }
    if (-not $NoBrowser) {
        Start-Process -FilePath ([string]$receipt.origin + '/scenarios')
    }
    Write-SsaJsonResult -Value @{
        state = 'RUNNING'
        app_version = [string]$receipt.app_version
        build_version = [string]$receipt.build_version
        database_path = [string]$receipt.database_path
        database_schema_version = [int]$receipt.database_schema_version
        data_dir = $root
        origin = [string]$receipt.origin
        pid = [int]$receipt.pid
        port = [int]$receipt.port
        receipt_path = $paths.Receipt
    }
    $child.Dispose()
    $child = $null
    Exit-SsaLifecycleOperationLock -Stream $operationLock
    $operationLock = $null
    exit 0
}
catch {
    $failureMessage = [string]$_.Exception.Message
    $cleanupFailed = $false
    $childExited = $false
    try {
        if ($childWasLaunched -and $null -ne $child) {
            try {
                try {
                    $child.Refresh()
                    if (-not $child.HasExited) {
                        try { $child.Kill() }
                        catch { }
                    }
                }
                catch { }
                try {
                    $childExited = [bool]$child.WaitForExit(5000)
                }
                catch {
                    try {
                        $child.Refresh()
                        $childExited = [bool]$child.HasExited
                    }
                    catch { $childExited = $false }
                }
                if (-not $childExited) { $cleanupFailed = $true }
            }
            finally {
                $child.Dispose()
                $child = $null
            }
        }
        if (
            $childWasLaunched -and
            $childExited -and
            $null -ne $paths -and
            (
                [IO.File]::Exists($paths.Receipt) -or
                [IO.File]::Exists($paths.Lock)
            )
        ) {
            try { Remove-SsaStaleLease -Paths $paths }
            catch { $cleanupFailed = $true }
        }
    }
    finally {
        if ($null -ne $operationLock) {
            Exit-SsaLifecycleOperationLock -Stream $operationLock
            $operationLock = $null
        }
    }
    if ($cleanupFailed) {
        $failureMessage += '; START_FAILURE_CLEANUP_FAILED'
    }
    Write-Error -ErrorId 'SSA_START_FAILED' -Message $failureMessage
    exit 1
}
