# SYNTHETIC-SALES-ASSIST-AUTHORED-M5
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$script:SsaReceiptSchema = 'synthetic-sales-assist-runtime-receipt/v1'
$script:SsaApiSchema = 'synthetic-sales-assist-api/v1'
$script:SsaApiRequestSchema = 'synthetic-sales-assist-api-request/v1'
$script:SsaAppVersion = '0.1.0'
$script:SsaBuildVersion = 'synthetic-sales-assist-m5/v1'
$script:SsaDatabaseFilename = 'synthetic_sales_assist.sqlite3'
$script:SsaReceiptFilename = 'service.json'
$script:SsaReceiptMembers = @(
    'app_version',
    'build_version',
    'csrf_token',
    'database_path',
    'database_schema_version',
    'host',
    'origin',
    'pid',
    'port',
    'process_identity_token',
    'process_start_time',
    'schema_version',
    'shutdown_token'
)
$script:SsaSafetyCounterNames = @(
    'PRODUCTION_SYSTEM_ACCESS_COUNT',
    'PRODUCTION_MUTATION_REQUEST_COUNT',
    'REAL_CUSTOMER_IDENTITY_COUNT',
    'NON_SYNTHETIC_FIXTURE_COUNT',
    'SECRET_MATERIAL_COUNT',
    'EXTERNAL_PRODUCTION_SYSTEM_ACCESS_COUNT',
    'EXTERNAL_MUTATION_REQUEST_COUNT',
    'NON_LOCALHOST_RUNTIME_REQUEST_COUNT',
    'REAL_CUSTOMER_DATA_COUNT'
)

function Get-SsaUnavailableSafetyCounters {
    $result = @{}
    foreach ($name in $script:SsaSafetyCounterNames) { $result[$name] = $null }
    return $result
}

function Resolve-SsaPythonPath {
    param([string]$PythonPath = 'python')

    $normalizedInput = $PythonPath.Replace('/', '\')
    if (
        [string]::IsNullOrWhiteSpace($PythonPath) -or
        $PythonPath.Contains('"') -or
        $PythonPath.Contains([char]0) -or
        $PythonPath -match '^[A-Za-z][A-Za-z0-9+.-]*://' -or
        $normalizedInput.StartsWith('\\') -or
        $normalizedInput.StartsWith('\\?\') -or
        $normalizedInput.StartsWith('\\.\')
    ) {
        throw 'PYTHON_PATH_INVALID'
    }
    if ([IO.Path]::IsPathRooted($PythonPath)) {
        $inputFullPath = [IO.Path]::GetFullPath($PythonPath)
        $inputRoot = [IO.Path]::GetPathRoot($inputFullPath)
        $inputTail = $inputFullPath.Substring($inputRoot.Length)
        if ($inputTail.Contains(':')) { throw 'PYTHON_PATH_INVALID' }
        try {
            if ([IO.DriveInfo]::new($inputRoot).DriveType -eq [IO.DriveType]::Network) {
                throw 'PYTHON_PATH_REMOTE_DRIVE_PROHIBITED'
            }
        }
        catch [ArgumentException] { throw 'PYTHON_PATH_INVALID' }
    }
    $command = Get-Command -Name $PythonPath -CommandType Application -ErrorAction Stop |
        Select-Object -First 1
    $resolved = [IO.Path]::GetFullPath([string]$command.Source)
    if ($resolved.Replace('/', '\').StartsWith('\\')) {
        throw 'PYTHON_PATH_NETWORK_PROHIBITED'
    }
    if (-not [IO.File]::Exists($resolved)) {
        throw 'PYTHON_PATH_INVALID'
    }
    $root = [IO.Path]::GetPathRoot($resolved)
    if ([string]::IsNullOrWhiteSpace($root)) { throw 'PYTHON_PATH_INVALID' }
    $tail = $resolved.Substring($root.Length)
    if ($tail.Contains(':')) { throw 'PYTHON_PATH_INVALID' }
    try {
        if ([IO.DriveInfo]::new($root).DriveType -eq [IO.DriveType]::Network) {
            throw 'PYTHON_PATH_REMOTE_DRIVE_PROHIBITED'
        }
    }
    catch [ArgumentException] { throw 'PYTHON_PATH_INVALID' }
    $candidate = $resolved
    while (-not [string]::IsNullOrEmpty($candidate)) {
        if (Test-Path -LiteralPath $candidate) {
            $item = Get-Item -LiteralPath $candidate -Force
            if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw 'PYTHON_PATH_REPARSE_POINT'
            }
        }
        $parent = [IO.Directory]::GetParent($candidate)
        if ($null -eq $parent) { break }
        $candidate = $parent.FullName
    }
    $executable = Get-Item -LiteralPath $resolved -Force
    if ($executable -isnot [IO.FileInfo]) { throw 'PYTHON_PATH_INVALID' }
    return $resolved
}

function Resolve-SsaDataRoot {
    param([string]$DataDir)

    if ([string]::IsNullOrWhiteSpace($DataDir)) {
        if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
            throw 'LOCALAPPDATA_UNAVAILABLE'
        }
        $DataDir = Join-Path $env:LOCALAPPDATA 'SyntheticSalesAssist'
    }
    if (
        $DataDir.Contains([char]0) -or
        $DataDir.Contains('"') -or
        $DataDir -match '^[A-Za-z][A-Za-z0-9+.-]*://' -or
        $DataDir.StartsWith('\\') -or
        $DataDir.StartsWith('//')
    ) {
        throw 'DATA_DIR_NOT_LOCAL'
    }
    $segments = $DataDir -split '[\\/]'
    if ($segments -contains '..' -or -not [IO.Path]::IsPathRooted($DataDir)) {
        throw 'DATA_DIR_ABSOLUTE_REQUIRED'
    }
    $resolved = [IO.Path]::GetFullPath($DataDir)
    $pathRoot = [IO.Path]::GetPathRoot($resolved)
    if ([string]::IsNullOrWhiteSpace($pathRoot)) {
        throw 'DATA_DIR_ABSOLUTE_REQUIRED'
    }
    $tail = $resolved.Substring($pathRoot.Length)
    if ($tail.Contains(':')) { throw 'DATA_DIR_ALTERNATE_DATA_STREAM' }
    if (
        $resolved.TrimEnd([IO.Path]::DirectorySeparatorChar).Equals(
            $pathRoot.TrimEnd([IO.Path]::DirectorySeparatorChar),
            [StringComparison]::OrdinalIgnoreCase
        )
    ) {
        throw 'DATA_DIR_DRIVE_ROOT_PROHIBITED'
    }
    try {
        $drive = [IO.DriveInfo]::new($pathRoot)
        if ($drive.DriveType -eq [IO.DriveType]::Network) {
            throw 'DATA_DIR_REMOTE_DRIVE_PROHIBITED'
        }
    }
    catch [ArgumentException] {
        throw 'DATA_DIR_DRIVE_INVALID'
    }
    $repository = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
    $repositoryPrefix = $repository.TrimEnd([IO.Path]::DirectorySeparatorChar) +
        [IO.Path]::DirectorySeparatorChar
    if (
        $resolved.Equals($repository, [StringComparison]::OrdinalIgnoreCase) -or
        $resolved.StartsWith($repositoryPrefix, [StringComparison]::OrdinalIgnoreCase)
    ) {
        throw 'DATA_DIR_REPOSITORY_PROHIBITED'
    }

    $candidate = $resolved
    while (-not [string]::IsNullOrEmpty($candidate)) {
        if (Test-Path -LiteralPath $candidate) {
            $item = Get-Item -LiteralPath $candidate -Force
            if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw 'DATA_DIR_REPARSE_POINT'
            }
        }
        $parent = [IO.Directory]::GetParent($candidate)
        if ($null -eq $parent) { break }
        $candidate = $parent.FullName
    }
    return $resolved.TrimEnd(
        [IO.Path]::DirectorySeparatorChar,
        [IO.Path]::AltDirectorySeparatorChar
    )
}

function Get-SsaRuntimePaths {
    param([Parameter(Mandatory = $true)][string]$DataRoot)

    $data = Join-Path $DataRoot 'data'
    $runtime = Join-Path $DataRoot 'runtime'
    $receipt = Join-Path $runtime $script:SsaReceiptFilename
    [PSCustomObject]@{
        Root = $DataRoot
        Data = $data
        Logs = Join-Path $DataRoot 'logs'
        Backups = Join-Path $DataRoot 'backups'
        Runtime = $runtime
        Database = Join-Path $data $script:SsaDatabaseFilename
        ActivityLock = Join-Path $data ('.' + $script:SsaDatabaseFilename + '.activity.lock')
        Receipt = $receipt
        Lock = $receipt + '.lock'
        LifecycleLock = Join-Path $runtime 'lifecycle-operation.lock'
    }
}

function Assert-SsaControlledDirectory {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
        throw 'CONTROLLED_DIRECTORY_UNAVAILABLE'
    }
    $item = Get-Item -LiteralPath $Path -Force
    if (
        $item -isnot [IO.DirectoryInfo] -or
        ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0
    ) {
        throw 'CONTROLLED_DIRECTORY_REPARSE_POINT'
    }
}

function Initialize-SsaDirectories {
    param([Parameter(Mandatory = $true)]$Paths)

    foreach ($path in @(
        $Paths.Root,
        $Paths.Data,
        $Paths.Logs,
        $Paths.Backups,
        $Paths.Runtime
    )) {
        if (-not (Test-Path -LiteralPath $path)) {
            [void](New-Item -ItemType Directory -Path $path -Force)
        }
        Assert-SsaControlledDirectory -Path $path
    }
}

function Assert-SsaRuntimeFileNotReparsePoint {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (Test-Path -LiteralPath $Path) {
        $item = Get-Item -LiteralPath $Path -Force
        if (
            $item -isnot [IO.FileInfo] -or
            ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0
        ) {
            throw 'RUNTIME_FILE_REPARSE_POINT'
        }
    }
}

function Invoke-SsaCliJson {
    param(
        [Parameter(Mandatory = $true)][string]$PythonPath,
        [Parameter(Mandatory = $true)][string]$DataRoot,
        [Parameter(Mandatory = $true)][string[]]$CommandArguments
    )

    $arguments = @(
        '-m',
        'synthetic_sales_assist.cli',
        '--json',
        '--data-dir',
        $DataRoot
    ) + $CommandArguments
    $sourceRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\src'))
    Push-Location -LiteralPath $sourceRoot
    try {
        $lines = @(& $PythonPath @arguments 2>&1)
        $cliExitCode = $LASTEXITCODE
    }
    finally {
        Pop-Location
    }
    if ($cliExitCode -ne 0) {
        throw 'CLI_COMMAND_FAILED'
    }
    try {
        $envelope = ($lines -join [Environment]::NewLine) | ConvertFrom-Json
    }
    catch {
        throw 'CLI_RESPONSE_INVALID'
    }
    if ($null -eq $envelope -or $envelope.ok -ne $true) {
        throw 'CLI_COMMAND_FAILED'
    }
    return $envelope
}

function Read-SsaRuntimeReceipt {
    param(
        [Parameter(Mandatory = $true)][string]$ReceiptPath,
        [Parameter(Mandatory = $true)][string]$ExpectedDataRoot
    )

    Assert-SsaControlledDirectory -Path ([IO.Path]::GetDirectoryName($ReceiptPath))
    Assert-SsaRuntimeFileNotReparsePoint -Path $ReceiptPath
    if (-not [IO.File]::Exists($ReceiptPath)) {
        return $null
    }
    try {
        $raw = [IO.File]::ReadAllText($ReceiptPath, [Text.Encoding]::UTF8)
        $receipt = $raw | ConvertFrom-Json
    }
    catch {
        throw 'RUNTIME_RECEIPT_INVALID'
    }
    $actualMembers = @($receipt.PSObject.Properties.Name | Sort-Object)
    $expectedMembers = @($script:SsaReceiptMembers | Sort-Object)
    if (($actualMembers -join "`n") -cne ($expectedMembers -join "`n")) {
        throw 'RUNTIME_RECEIPT_MEMBERS_INVALID'
    }
    try {
        $pidValue = [int]$receipt.pid
        $portValue = [int]$receipt.port
        $databaseSchema = [int]$receipt.database_schema_version
    }
    catch {
        throw 'RUNTIME_RECEIPT_INVALID'
    }
    if (
        $receipt.schema_version -cne $script:SsaReceiptSchema -or
        $receipt.host -cne '127.0.0.1' -or
        $receipt.pid -ne $pidValue -or
        $pidValue -le 0 -or
        $receipt.port -ne $portValue -or
        $portValue -lt 1 -or
        $portValue -gt 65535 -or
        $receipt.database_schema_version -ne $databaseSchema -or
        $databaseSchema -ne 4 -or
        [string]::IsNullOrWhiteSpace([string]$receipt.app_version) -or
        ([string]$receipt.app_version).Length -gt 64 -or
        [string]::IsNullOrWhiteSpace([string]$receipt.build_version) -or
        ([string]$receipt.build_version).Length -gt 128 -or
        [string]$receipt.csrf_token -notmatch '^[0-9a-f]{64}$' -or
        [string]$receipt.process_identity_token -notmatch '^[0-9a-f]{64}$' -or
        [string]$receipt.shutdown_token -notmatch '^[0-9a-f]{64}$' -or
        [string]$receipt.csrf_token -ceq [string]$receipt.shutdown_token -or
        [string]$receipt.csrf_token -ceq
            [string]$receipt.process_identity_token -or
        [string]$receipt.shutdown_token -ceq
            [string]$receipt.process_identity_token
    ) {
        throw 'RUNTIME_RECEIPT_INVALID'
    }
    $expectedOrigin = 'http://127.0.0.1:{0}' -f $receipt.port
    $expectedDatabase = [IO.Path]::GetFullPath(
        (Join-Path (Join-Path $ExpectedDataRoot 'data') $script:SsaDatabaseFilename)
    )
    if (
        [string]$receipt.origin -cne $expectedOrigin -or
        -not [IO.Path]::IsPathRooted([string]$receipt.database_path) -or
        -not ([IO.Path]::GetFullPath([string]$receipt.database_path)).Equals(
            $expectedDatabase,
            [StringComparison]::OrdinalIgnoreCase
        )
    ) {
        throw 'RUNTIME_RECEIPT_SCOPE_INVALID'
    }
    try {
        [void][DateTimeOffset]::Parse(
            [string]$receipt.process_start_time,
            [Globalization.CultureInfo]::InvariantCulture,
            [Globalization.DateTimeStyles]::AssumeUniversal
        )
    }
    catch {
        throw 'RUNTIME_RECEIPT_START_TIME_INVALID'
    }
    return $receipt
}

function Get-SsaOwnedProcess {
    param(
        [Parameter(Mandatory = $true)]$Receipt,
        [Parameter(Mandatory = $true)][string]$PythonPath,
        [Parameter(Mandatory = $true)][string]$DataRoot,
        [Parameter(Mandatory = $true)][string]$ReceiptPath,
        [Parameter(Mandatory = $true)][string]$LockPath
    )

    $process = Get-Process -Id ([int]$Receipt.pid) -ErrorAction SilentlyContinue
    if ($null -eq $process) { return $null }
    Assert-SsaRuntimeFileNotReparsePoint -Path $LockPath
    if (-not [IO.File]::Exists($LockPath)) { throw 'PROCESS_LEASE_MISSING' }
    $leaseReader = $null
    $leaseWasFree = $false
    try {
        $leaseReader = [IO.FileStream]::new(
            $LockPath,
            [IO.FileMode]::Open,
            [IO.FileAccess]::Read,
            [IO.FileShare]::ReadWrite,
            1,
            [IO.FileOptions]::None
        )
        if ($leaseReader.Length -ne 64) { throw 'PROCESS_LEASE_LENGTH_INVALID' }
        $identityBytes = [byte[]]::new(64)
        if ($leaseReader.Read($identityBytes, 0, 64) -ne 64) {
            throw 'PROCESS_LEASE_LENGTH_INVALID'
        }
        $lockIdentity = [Text.Encoding]::ASCII.GetString($identityBytes)
        try {
            $leaseReader.Lock(64, 1)
            $leaseWasFree = $true
        }
        catch [IO.IOException] { $leaseWasFree = $false }
        if ($leaseWasFree) { try { $leaseReader.Unlock(64, 1) } catch { } }
    }
    catch { throw 'PROCESS_LEASE_UNREADABLE' }
    finally {
        if ($null -ne $leaseReader) { $leaseReader.Dispose() }
    }
    if ($leaseWasFree) { throw 'PROCESS_LEASE_NOT_HELD' }
    if ($lockIdentity -cne [string]$Receipt.process_identity_token) {
        throw 'PROCESS_LEASE_IDENTITY_MISMATCH'
    }
    $expectedStart = [DateTimeOffset]::Parse(
        [string]$Receipt.process_start_time,
        [Globalization.CultureInfo]::InvariantCulture,
        [Globalization.DateTimeStyles]::AssumeUniversal
    ).UtcDateTime
    $actualStart = $process.StartTime.ToUniversalTime()
    if ([Math]::Abs(($actualStart - $expectedStart).TotalSeconds) -gt 1.0) {
        throw 'PROCESS_START_TIME_MISMATCH'
    }
    if ([string]::IsNullOrWhiteSpace([string]$process.Path)) {
        throw 'PROCESS_EXECUTABLE_UNAVAILABLE'
    }
    $actualExecutable = [IO.Path]::GetFullPath([string]$process.Path)
    if (-not $actualExecutable.Equals($PythonPath, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'PROCESS_EXECUTABLE_MISMATCH'
    }
    return $process
}

function Invoke-SsaHealth {
    param([Parameter(Mandatory = $true)]$Receipt)

    $headers = @{ Host = '127.0.0.1:{0}' -f [int]$Receipt.port }
    $response = Invoke-WebRequest -Uri ([string]$Receipt.origin + '/health') `
        -Method Get -Headers $headers -UseBasicParsing -TimeoutSec 2
    if ($response.StatusCode -ne 200) { throw 'HEALTH_CHECK_FAILED' }
    try { $health = $response.Content | ConvertFrom-Json }
    catch { throw 'HEALTH_RESPONSE_INVALID' }
    $members = @($health.PSObject.Properties.Name | Sort-Object)
    if (@(Compare-Object $members @('data', 'schema_version')).Count -ne 0 -or
        $health.schema_version -cne $script:SsaApiSchema -or
        $null -eq $health.data) {
        throw 'HEALTH_RESPONSE_INVALID'
    }
    if ($health.data.status -cne 'PASS') { throw 'HEALTH_STATUS_NOT_PASS' }
    if (
        [string]$health.data.app_version -cne [string]$Receipt.app_version -or
        [string]$health.data.build_version -cne [string]$Receipt.build_version -or
        [int]$health.data.database_schema_version -ne
            [int]$Receipt.database_schema_version
    ) {
        throw 'HEALTH_IDENTITY_MISMATCH'
    }
    return $health
}

function Get-SsaLastHealthStatus {
    param([Parameter(Mandatory = $true)]$Receipt)

    $request = [Net.HttpWebRequest]::Create([string]$Receipt.origin + '/health')
    $request.Method = 'GET'
    $request.Host = '127.0.0.1:{0}' -f [int]$Receipt.port
    $request.AllowAutoRedirect = $false
    $request.Timeout = 2000
    $request.ReadWriteTimeout = 2000
    $response = $null
    try {
        try {
            $response = $request.GetResponse()
        }
        catch [Net.WebException] {
            $response = $_.Exception.Response
            if ($null -eq $response) { return 'UNAVAILABLE' }
        }
        $reader = [IO.StreamReader]::new(
            $response.GetResponseStream(),
            [Text.Encoding]::UTF8,
            $true,
            1024,
            $false
        )
        try { $content = $reader.ReadToEnd() }
        finally { $reader.Dispose() }
        try { $health = $content | ConvertFrom-Json }
        catch { return 'UNAVAILABLE' }
        $members = @($health.PSObject.Properties.Name | Sort-Object)
        if (
            @(Compare-Object $members @('data', 'schema_version')).Count -ne 0 -or
            $health.schema_version -cne $script:SsaApiSchema -or
            $null -eq $health.data
        ) {
            return 'UNAVAILABLE'
        }
        if ($health.data.status -ceq 'FAIL') { return 'FAIL' }
        if (
            $health.data.status -ceq 'PASS' -and
            [int]$response.StatusCode -eq 200
        ) {
            return 'PASS'
        }
        return 'UNAVAILABLE'
    }
    catch { return 'UNAVAILABLE' }
    finally {
        if ($null -ne $response) { $response.Dispose() }
    }
}

function Invoke-SsaOwnedShutdown {
    param([Parameter(Mandatory = $true)]$Receipt)

    $headers = @{
        Host = '127.0.0.1:{0}' -f [int]$Receipt.port
        Origin = [string]$Receipt.origin
        'X-SSA-CSRF-Token' = [string]$Receipt.csrf_token
        'X-SSA-Shutdown-Token' = [string]$Receipt.shutdown_token
    }
    $body = '{"schema_version":"synthetic-sales-assist-api-request/v1"}'
    $response = Invoke-WebRequest -Uri ([string]$Receipt.origin + '/api/v1/system/shutdown') `
        -Method Post -Headers $headers -ContentType 'application/json' -Body $body `
        -UseBasicParsing -TimeoutSec 5
    if ($response.StatusCode -ne 202) { throw 'OWNED_SHUTDOWN_REJECTED' }
}

function Enter-SsaLeaseCleanupLock {
    param([Parameter(Mandatory = $true)][string]$LockPath)

    Assert-SsaControlledDirectory -Path ([IO.Path]::GetDirectoryName($LockPath))
    Assert-SsaRuntimeFileNotReparsePoint -Path $LockPath
    $stream = [IO.File]::Open(
        $LockPath,
        [IO.FileMode]::OpenOrCreate,
        [IO.FileAccess]::ReadWrite,
        [IO.FileShare]::ReadWrite
    )
    try {
        if ($stream.Length -lt 64) {
            $stream.SetLength(64)
            $stream.Flush($true)
        }
        $stream.Lock(64, 1)
        return $stream
    }
    catch {
        $stream.Dispose()
        throw 'RUNTIME_LEASE_HELD'
    }
}

function Enter-SsaLifecycleOperationLock {
    param([Parameter(Mandatory = $true)][string]$LockPath)

    Assert-SsaControlledDirectory -Path ([IO.Path]::GetDirectoryName($LockPath))
    Assert-SsaRuntimeFileNotReparsePoint -Path $LockPath
    $stream = [IO.File]::Open(
        $LockPath,
        [IO.FileMode]::OpenOrCreate,
        [IO.FileAccess]::ReadWrite,
        [IO.FileShare]::ReadWrite
    )
    try {
        if ($stream.Length -lt 1) {
            $stream.SetLength(1)
            $stream.Flush($true)
        }
        $stream.Lock(0, 1)
        return $stream
    }
    catch {
        $stream.Dispose()
        throw 'LIFECYCLE_OPERATION_ACTIVE'
    }
}

function Exit-SsaLifecycleOperationLock {
    param([Parameter(Mandatory = $true)]$Stream)

    try { $Stream.Unlock(0, 1) } catch { }
    $Stream.Dispose()
}

function Remove-SsaStaleLease {
    param([Parameter(Mandatory = $true)]$Paths)

    $stream = Enter-SsaLeaseCleanupLock -LockPath $Paths.Lock
    try {
        if ([IO.File]::Exists($Paths.Receipt)) {
            Remove-Item -LiteralPath $Paths.Receipt -Force
        }
    }
    finally {
        try { $stream.Unlock(64, 1) } catch { }
        $stream.Dispose()
    }
    if ([IO.File]::Exists($Paths.Lock)) {
        Remove-Item -LiteralPath $Paths.Lock -Force
    }
}

function ConvertTo-SsaQuotedProcessArgument {
    param([Parameter(Mandatory = $true)][string]$Value)

    if ($Value.Contains('"')) { throw 'PROCESS_ARGUMENT_INVALID' }
    return '"' + $Value + '"'
}

function Write-SsaJsonResult {
    param([Parameter(Mandatory = $true)][hashtable]$Value)

    $Value | ConvertTo-Json -Compress -Depth 20
}
