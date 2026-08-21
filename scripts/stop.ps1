# SYNTHETIC-SALES-ASSIST-AUTHORED-M5
[CmdletBinding()]
param(
    [string]$PythonPath = 'python',
    [string]$DataDir,
    [ValidateRange(2, 60)][int]$ShutdownTimeoutSeconds = 15
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'lifecycle-common.ps1')

try {
    $python = Resolve-SsaPythonPath -PythonPath $PythonPath
    $root = Resolve-SsaDataRoot -DataDir $DataDir
    $paths = Get-SsaRuntimePaths -DataRoot $root
    if (Test-Path -LiteralPath $paths.Runtime) {
        Assert-SsaControlledDirectory -Path $paths.Runtime
    }
    if (-not [IO.File]::Exists($paths.Receipt)) {
        $stale = [IO.File]::Exists($paths.Lock)
        if ($stale) { Remove-SsaStaleLease -Paths $paths }
        Write-SsaJsonResult -Value @{ state = 'STOPPED'; data_dir = $root; stale = $stale }
        exit 0
    }

    $receipt = Read-SsaRuntimeReceipt -ReceiptPath $paths.Receipt -ExpectedDataRoot $root
    $owned = Get-SsaOwnedProcess -Receipt $receipt -PythonPath $python -DataRoot $root `
        -ReceiptPath $paths.Receipt -LockPath $paths.Lock
    if ($null -eq $owned) {
        Remove-SsaStaleLease -Paths $paths
        Write-SsaJsonResult -Value @{ state = 'STOPPED'; data_dir = $root; stale = $true }
        exit 0
    }

    Invoke-SsaOwnedShutdown -Receipt $receipt
    $deadline = [DateTime]::UtcNow.AddSeconds($ShutdownTimeoutSeconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        if ($null -eq (Get-Process -Id ([int]$receipt.pid) -ErrorAction SilentlyContinue)) {
            break
        }
        Start-Sleep -Milliseconds 200
    }
    if ($null -ne (Get-Process -Id ([int]$receipt.pid) -ErrorAction SilentlyContinue)) {
        throw 'OWNED_SHUTDOWN_TIMEOUT'
    }
    if ([IO.File]::Exists($paths.Receipt) -or [IO.File]::Exists($paths.Lock)) {
        Remove-SsaStaleLease -Paths $paths
    }
    Write-SsaJsonResult -Value @{
        state = 'STOPPED'
        data_dir = $root
        pid = [int]$receipt.pid
        stale = $false
    }
    exit 0
}
catch {
    Write-Error -ErrorId 'SSA_STOP_FAILED' -Message ([string]$_.Exception.Message)
    exit 1
}
