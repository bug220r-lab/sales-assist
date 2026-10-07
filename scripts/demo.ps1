# SYNTHETIC-SALES-ASSIST-AUTHORED-M8
[CmdletBinding()]
param(
    [ValidateSet('Start', 'Stop', 'Status', 'Backup', 'Reset', 'Upgrade', 'Remove')]
    [string]$Action = 'Start',
    [string]$DataDir,
    [ValidateRange(1024, 65535)][int]$Port = 8905,
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
$portWasBound = $PSBoundParameters.ContainsKey('Port')
try {
    if ($Action -eq 'Start') {
        Write-Host 'Opening Sales Assist. Checking the application files and runtime...'
    }
    $metadataPath = Join-Path $installation 'release-build.json'
    Assert-SsaRuntimeFileNotReparsePoint -Path $metadataPath
    $metadata = Get-Content -LiteralPath $metadataPath -Raw | ConvertFrom-Json
    if ($metadata.schema -cne 'synthetic-sales-assist-release-build/v1' -or
        $metadata.release_id -cnotmatch '^demo-[0-9]+\.[0-9]+\.[0-9]+-[0-9a-f]{12}$' -or
        $null -eq $metadata.PSObject.Properties['distribution_revision'] -or
        $metadata.distribution_revision -cne 'doi-v7-daily-local-20261006') {
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
        & $python -B -I $support verify --install-root $installation
        if ($LASTEXITCODE -ne 0) { throw 'RELEASE_PAYLOAD_VERIFICATION_FAILED' }
    }
    if ($Action -eq 'Upgrade' -and [string]::IsNullOrWhiteSpace($DataDir)) {
        $DataDir = Read-Host 'Absolute path of the disposable demo data root to upgrade'
    }
    if ([string]::IsNullOrWhiteSpace($DataDir)) {
        $dataRootJson = & $python -B -I $support data-root --install-root $installation
        if ($LASTEXITCODE -ne 0) { throw 'DEMO_DATA_ROOT_UNAVAILABLE' }
        $DataDir = ($dataRootJson | ConvertFrom-Json).data_dir
    }
    $dataRoot = Resolve-SsaDataRoot -DataDir $DataDir
    switch ($Action) {
        'Start' {
            $dailyPolicySupport = Join-Path $installation 'tools\daily_policy.py'
            $policyLines = @(& $python -B -I $dailyPolicySupport check --data-dir $dataRoot)
            if ($LASTEXITCODE -ne 0) { throw 'DOI_PRIVATE_POLICY_REQUIRED_SEE_PRIVATE_CONFIGURATION' }
            $statusLines = @(& (Join-Path $PSScriptRoot 'status.ps1') -DataDir $dataRoot)
            if ($LASTEXITCODE -ne 0) { throw 'DEMO_OWNED_STATUS_UNAVAILABLE' }
            try { $currentStatus = ($statusLines -join "`n") | ConvertFrom-Json }
            catch { throw 'DEMO_OWNED_STATUS_INVALID' }
            if ($currentStatus.state -ceq 'RUNNING') {
                if ($currentStatus.last_health_status -cne 'PASS') {
                    throw 'DEMO_RUNNING_SERVICE_UNHEALTHY'
                }
                if ($portWasBound -and $Port -ne [int]$currentStatus.port) {
                    throw 'DEMO_RUNNING_PORT_MISMATCH'
                }
                $markerPath = Join-Path $dataRoot 'demo-release.json'
                Assert-SsaRuntimeFileNotReparsePoint -Path $markerPath
                if (-not [IO.File]::Exists($markerPath)) {
                    throw 'DEMO_RUNNING_RELEASE_MARKER_MISSING'
                }
                if ((Get-Item -LiteralPath $markerPath).Length -gt 1MB) {
                    throw 'DEMO_RUNNING_RELEASE_MISMATCH'
                }
                try { $marker = [IO.File]::ReadAllText($markerPath) | ConvertFrom-Json }
                catch { throw 'DEMO_RUNNING_RELEASE_MISMATCH' }
                if ($null -eq $marker -or
                    $null -eq $marker.PSObject.Properties['schema'] -or
                    $null -eq $marker.PSObject.Properties['source_commit'] -or
                    $null -eq $marker.PSObject.Properties['distribution_revision'] -or
                    $marker.distribution_revision -cne $metadata.distribution_revision -or
                    $marker.schema -cne 'synthetic-sales-assist-release-build/v1' -or
                    $marker.source_commit -cne $metadata.source_commit) {
                    throw 'DEMO_RUNNING_RELEASE_MISMATCH'
                }
                $policyBinding = @(& $python -B -I $dailyPolicySupport verify-running --data-dir $dataRoot)
                if ($LASTEXITCODE -ne 0) { throw 'DOI_POLICY_CHANGED_STOP_OWNED_SERVICE_BEFORE_RESTART' }
                & $python -B -I $support configure --install-root $installation --data-dir $dataRoot
                if ($LASTEXITCODE -ne 0) { throw 'DEMO_DATA_ROOT_CONFIGURATION_FAILED' }
                if (-not $NoBrowser) {
                    Start-Process -FilePath ([string]$currentStatus.origin + '/doi-csv-review')
                }
                Write-SsaJsonResult -Value @{
                    state = 'REOPENED'
                    origin = [string]$currentStatus.origin
                    pid = [int]$currentStatus.pid
                    port = [int]$currentStatus.port
                    data_dir = $dataRoot
                    source_commit = [string]$metadata.source_commit
                }
                break
            }
            if ($currentStatus.state -cnotin @('STOPPED', 'STALE')) {
                throw 'DEMO_OWNED_STATUS_INVALID'
            }
            if (-not $portWasBound) {
                $reservation = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, $Port)
                $reservation.ExclusiveAddressUse = $true
                try {
                    try { $reservation.Start() }
                    catch {
                        $socketFailure = $_.Exception
                        while ($socketFailure -isnot [Net.Sockets.SocketException] -and
                            $null -ne $socketFailure.InnerException) {
                            $socketFailure = $socketFailure.InnerException
                        }
                        if ($socketFailure -isnot [Net.Sockets.SocketException] -or
                            $socketFailure.SocketErrorCode -ne
                            [Net.Sockets.SocketError]::AddressAlreadyInUse) {
                            throw 'DEMO_DEFAULT_PORT_UNAVAILABLE'
                        }
                        $reservation.Stop()
                        $reservation = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, 0)
                        $reservation.ExclusiveAddressUse = $true
                        $reservation.Start()
                        $Port = [int]$reservation.LocalEndpoint.Port
                    }
                }
                finally { $reservation.Stop() }
                # The reservation only selects a candidate; the ordinary owned
                # startup must still bind it successfully. A race fails normally.
            }
            & (Join-Path $PSScriptRoot 'start.ps1') -DataDir $dataRoot -Port $Port `
                -NoBrowser -PrepareDemo
            if ($LASTEXITCODE -ne 0) { throw 'DEMO_START_FAILED' }
            & $python -B -I $support configure --install-root $installation --data-dir $dataRoot
            if ($LASTEXITCODE -ne 0) {
                & (Join-Path $PSScriptRoot 'stop.ps1') -DataDir $dataRoot
                throw 'DEMO_DATA_ROOT_CONFIGURATION_FAILED'
            }
            if (-not $NoBrowser) { Start-Process "http://127.0.0.1:$Port/doi-csv-review" }
        }
        'Upgrade' {
            # start.ps1 holds the lifecycle lock through verified backup, preparation,
            # startup and ownership checks. An active service fails before preparation.
            & (Join-Path $PSScriptRoot 'start.ps1') -DataDir $dataRoot -NoBrowser `
                -Port $Port -PrepareDemo -AllowSchema4Upgrade
            if ($LASTEXITCODE -ne 0) { throw 'DEMO_UPGRADE_FAILED_STOP_OWNED_SERVICE_FIRST' }
            & $python -B -I $support configure --install-root $installation --data-dir $dataRoot
            if ($LASTEXITCODE -ne 0) {
                & (Join-Path $PSScriptRoot 'stop.ps1') -DataDir $dataRoot
                throw 'DEMO_DATA_ROOT_CONFIGURATION_FAILED'
            }
        }
        'Stop' { & (Join-Path $PSScriptRoot 'stop.ps1') -DataDir $dataRoot }
        'Status' { & (Join-Path $PSScriptRoot 'status.ps1') -DataDir $dataRoot }
        'Backup' {
            & $python -B -I $support backup --install-root $installation --data-dir $dataRoot
        }
        'Reset' {
            if (-not $Confirmed) {
                $answer = Read-Host ('Reset Sales Credit/DOI sample records after backup; ' +
                    'preserve campaign drafts/history in ' + $dataRoot + ' ? Type RESET')
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
                & $python -B -I $support remove --install-root $installation --confirm-remove
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
    Write-Host 'Keep the entire extracted package together, including its private python folder.'
    Write-Host 'The Windows application includes its runtime. No runtime is downloaded at startup.'
    Write-Host 'Older development packages require external CPython 3.12 with tzdata 2026.3.'
    Write-Host 'DOI daily launch requires the external private configuration described in PRIVATE_CONFIGURATION.md.'
    Write-Host 'If its policy changed while running, use this copy''s STOP.cmd before START.cmd. STATUS and STOP do not require that policy.'
    exit 1
}
finally {
    $env:PYTHONPATH = $oldPythonPath
    $env:SSA_PYTHON = $oldSsaPython
}
