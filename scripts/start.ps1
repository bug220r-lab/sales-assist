# SYNTHETIC-SALES-ASSIST-AUTHORED-M5
[CmdletBinding()]
param(
    [string]$PythonPath = 'python',
    [string]$DataDir,
    [ValidateRange(1024, 65535)][int]$Port = 8765,
    [switch]$NoBrowser,
    [ValidateRange(2, 60)][int]$StartupTimeoutSeconds = 20
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'lifecycle-common.ps1')

$child = $null
$operationLock = $null
try {
    $python = Resolve-SsaPythonPath -PythonPath $PythonPath
    $root = Resolve-SsaDataRoot -DataDir $DataDir
    $paths = Get-SsaRuntimePaths -DataRoot $root
    Initialize-SsaDirectories -Paths $paths
    $operationLock = Enter-SsaLifecycleOperationLock -LockPath $paths.LifecycleLock
    [void](Invoke-SsaCliJson -PythonPath $python -DataRoot $root `
        -CommandArguments @('doctor'))

    $prior = Read-SsaRuntimeReceipt -ReceiptPath $paths.Receipt -ExpectedDataRoot $root
    if ($null -ne $prior) {
        $owned = Get-SsaOwnedProcess -Receipt $prior -PythonPath $python -DataRoot $root `
            -ReceiptPath $paths.Receipt -LockPath $paths.Lock
        if ($null -ne $owned) { throw 'SERVICE_ALREADY_RUNNING' }
        Remove-SsaStaleLease -Paths $paths
    }
    elseif ([IO.File]::Exists($paths.Lock)) {
        Remove-SsaStaleLease -Paths $paths
    }

    $argumentLine = @(
        '-m synthetic_sales_assist.portal',
        '--data-dir ' + (ConvertTo-SsaQuotedProcessArgument $root),
        '--host 127.0.0.1',
        '--port ' + $Port,
        '--runtime-receipt ' + (ConvertTo-SsaQuotedProcessArgument $paths.Receipt)
    ) -join ' '
    $repository = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\src'))
    $child = Start-Process -FilePath $python -ArgumentList $argumentLine -PassThru `
        -WindowStyle Hidden -WorkingDirectory $repository

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
    $owned = Get-SsaOwnedProcess -Receipt $receipt -PythonPath $python -DataRoot $root `
        -ReceiptPath $paths.Receipt -LockPath $paths.Lock
    if ($null -eq $owned -or $owned.Id -ne $child.Id) { throw 'PROCESS_OWNERSHIP_MISMATCH' }
    Exit-SsaLifecycleOperationLock -Stream $operationLock
    $operationLock = $null

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
    exit 0
}
catch {
    if ($null -ne $operationLock) {
        Exit-SsaLifecycleOperationLock -Stream $operationLock
        $operationLock = $null
    }
    if ($null -ne $child) {
        $child.Refresh()
        if (-not $child.HasExited) {
            $child.Kill()
        }
        [void]$child.WaitForExit(5000)
        $child.Dispose()
    }
    Write-Error -ErrorId 'SSA_START_FAILED' -Message ([string]$_.Exception.Message)
    exit 1
}
