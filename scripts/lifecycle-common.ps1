# SYNTHETIC-SALES-ASSIST-AUTHORED-M5
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$script:SsaReceiptSchema = 'synthetic-sales-assist-runtime-receipt/v1'
$script:SsaApiSchema = 'synthetic-sales-assist-api/v1'
$script:SsaApiRequestSchema = 'synthetic-sales-assist-api-request/v1'
$script:SsaAppVersion = '0.1.2'
$script:SsaBuildVersion = 'synthetic-sales-assist-m8/v1'
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

function Get-SsaVerifiedCodexPythonPath {
    $profile = [Environment]::GetFolderPath(
        [Environment+SpecialFolder]::UserProfile
    )
    if ([string]::IsNullOrWhiteSpace($profile)) {
        $localAppData = [Environment]::GetFolderPath(
            [Environment+SpecialFolder]::LocalApplicationData
        )
        if ([string]::IsNullOrWhiteSpace($localAppData)) {
            throw 'PYTHON_CODEX_PROFILE_UNAVAILABLE'
        }
        $appData = [IO.Directory]::GetParent($localAppData)
        if ($null -eq $appData -or $null -eq $appData.Parent) {
            throw 'PYTHON_CODEX_PROFILE_UNAVAILABLE'
        }
        $profile = $appData.Parent.FullName
    }
    return [IO.Path]::GetFullPath((Join-Path $profile (
        '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
    )))
}

function Get-SsaFinalExecutablePath {
    param([Parameter(Mandatory = $true)][string]$Path)

    if ($null -eq ('SyntheticSalesAssist.Launcher.FinalPathNative' -as [type])) {
        $typeDefinition = @'
using System.Runtime.InteropServices;
using System.Text;
using Microsoft.Win32.SafeHandles;

namespace SyntheticSalesAssist.Launcher
{
    public static class FinalPathNative
    {
        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        public static extern uint GetFinalPathNameByHandle(
            SafeFileHandle file,
            StringBuilder path,
            uint pathLength,
            uint flags
        );
    }
}
'@
        try { Add-Type -TypeDefinition $typeDefinition -Language CSharp -ErrorAction Stop }
        catch { throw 'PYTHON_FINAL_PATH_RESOLVER_UNAVAILABLE' }
    }

    $share = [IO.FileShare]([int][IO.FileShare]::ReadWrite -bor [int][IO.FileShare]::Delete)
    try {
        $stream = [IO.File]::Open(
            $Path,
            [IO.FileMode]::Open,
            [IO.FileAccess]::Read,
            $share
        )
    }
    catch { throw 'PYTHON_FINAL_PATH_UNAVAILABLE' }
    try {
        $capacity = 32768
        $builder = [Text.StringBuilder]::new($capacity)
        $length = [SyntheticSalesAssist.Launcher.FinalPathNative]::GetFinalPathNameByHandle(
            $stream.SafeFileHandle,
            $builder,
            $capacity,
            0
        )
        if ($length -eq 0 -or $length -ge $capacity) {
            throw 'PYTHON_FINAL_PATH_UNAVAILABLE'
        }
        $finalPath = $builder.ToString()
    }
    finally { $stream.Dispose() }

    if (
        $finalPath.StartsWith('\\?\UNC\', [StringComparison]::OrdinalIgnoreCase) -or
        $finalPath.StartsWith('\\.\', [StringComparison]::OrdinalIgnoreCase) -or
        $finalPath.StartsWith('\??\', [StringComparison]::OrdinalIgnoreCase)
    ) {
        throw 'PYTHON_FINAL_PATH_NETWORK_OR_DEVICE_PROHIBITED'
    }
    if ($finalPath.StartsWith('\\?\', [StringComparison]::OrdinalIgnoreCase)) {
        $finalPath = $finalPath.Substring(4)
    }
    $resolved = Assert-SsaPythonProbePathLocal -Path $finalPath
    if (-not [IO.File]::Exists($resolved)) { throw 'PYTHON_FINAL_PATH_UNAVAILABLE' }
    $item = Get-Item -LiteralPath $resolved -Force
    if (
        $item -isnot [IO.FileInfo] -or
        ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0
    ) {
        throw 'PYTHON_FINAL_PATH_INVALID'
    }
    $candidate = [IO.Directory]::GetParent($resolved)
    while ($null -ne $candidate) {
        if (Test-Path -LiteralPath $candidate.FullName) {
            $ancestor = Get-Item -LiteralPath $candidate.FullName -Force
            if (($ancestor.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw 'PYTHON_FINAL_PATH_REPARSE_POINT'
            }
        }
        $candidate = $candidate.Parent
    }
    return $resolved
}

function Assert-SsaPythonProbePathLocal {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (
        [string]::IsNullOrWhiteSpace($Path) -or
        $Path.Contains('"') -or
        $Path.Contains([char]0) -or
        $Path -notmatch '^[A-Za-z]:[\\/]'
    ) {
        throw 'PYTHON_PROBE_PATH_INVALID'
    }
    try { $resolved = [IO.Path]::GetFullPath($Path) }
    catch { throw 'PYTHON_PROBE_PATH_INVALID' }
    $root = [IO.Path]::GetPathRoot($resolved)
    if ([string]::IsNullOrWhiteSpace($root)) { throw 'PYTHON_PROBE_PATH_INVALID' }
    if ($resolved.Substring($root.Length).Contains(':')) {
        throw 'PYTHON_PROBE_PATH_INVALID'
    }
    try {
        if ([IO.DriveInfo]::new($root).DriveType -eq [IO.DriveType]::Network) {
            throw 'PYTHON_PROBE_PATH_NETWORK_PROHIBITED'
        }
    }
    catch [ArgumentException] { throw 'PYTHON_PROBE_PATH_INVALID' }
    if (-not [IO.Path]::GetFileName($resolved).Equals(
        'python.exe',
        [StringComparison]::OrdinalIgnoreCase
    )) {
        throw 'PYTHON_PROBE_PATH_INVALID'
    }
    return $resolved
}

function Assert-SsaPythonProbeResult {
    param(
        [Parameter(Mandatory = $true)][string]$Output,
        [Parameter(Mandatory = $true)][string]$ExpectedPath,
        [Parameter(Mandatory = $true)][bool]$AllowLogicalPathDifference
    )

    $trimmed = $Output.Trim()
    if (
        [string]::IsNullOrWhiteSpace($trimmed) -or
        $trimmed.Contains("`r") -or
        $trimmed.Contains("`n") -or
        $trimmed.Length -gt 4096
    ) {
        throw 'PYTHON_VERSION_PROBE_INVALID'
    }
    $parts = @($trimmed.Split('|'))
    if ($parts.Count -ne 6 -or $parts[0] -cne 'SSA_PYTHON_PROBE_V1') {
        throw 'PYTHON_VERSION_PROBE_INVALID'
    }
    $major = 0
    $minor = 0
    if (
        -not [int]::TryParse($parts[1], [ref]$major) -or
        -not [int]::TryParse($parts[2], [ref]$minor)
    ) {
        throw 'PYTHON_VERSION_PROBE_INVALID'
    }
    if ($major -ne 3 -or $minor -ne 12) {
        throw 'PYTHON_VERSION_UNSUPPORTED'
    }
    if ($parts[3] -cne 'cpython') { throw 'PYTHON_IMPLEMENTATION_UNSUPPORTED' }
    $reportedPath = Assert-SsaPythonProbePathLocal -Path $parts[4]
    $finalPath = Assert-SsaPythonProbePathLocal -Path $parts[5]
    if (
        -not $AllowLogicalPathDifference -and
        (
            -not $reportedPath.Equals(
                $ExpectedPath,
                [StringComparison]::OrdinalIgnoreCase
            ) -or
            -not $finalPath.Equals(
                $ExpectedPath,
                [StringComparison]::OrdinalIgnoreCase
            )
        )
    ) {
        throw 'PYTHON_EXECUTABLE_IDENTITY_MISMATCH'
    }
    return [PSCustomObject]@{
        FinalPath = $finalPath
        ReportedPath = $reportedPath
    }
}

function Invoke-SsaPythonVersionProbe {
    param(
        [Parameter(Mandatory = $true)][string]$PythonPath,
        [Parameter(Mandatory = $true)][bool]$AllowLogicalPathDifference
    )

    $probeCode = "import os,sys;print('SSA_PYTHON_PROBE_V1|{}|{}|{}|{}|{}'.format(" +
        "sys.version_info[0],sys.version_info[1],sys.implementation.name," +
        "sys.executable,os.path.realpath(sys.executable)))"
    $startInfo = [Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $PythonPath
    $startInfo.Arguments = '-I -S -E -c "' + $probeCode + '"'
    $startInfo.CreateNoWindow = $true
    $startInfo.UseShellExecute = $false
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $process = [Diagnostics.Process]::new()
    $process.StartInfo = $startInfo
    try {
        try { $started = $process.Start() }
        catch { throw 'PYTHON_EXECUTABLE_INVALID' }
        if (-not $started) { throw 'PYTHON_EXECUTABLE_INVALID' }
        $stdoutTask = $process.StandardOutput.ReadToEndAsync()
        $stderrTask = $process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit(5000)) {
            try { $process.Kill() } catch { }
            [void]$process.WaitForExit(1000)
            throw 'PYTHON_VERSION_PROBE_TIMEOUT'
        }
        $stdout = $stdoutTask.GetAwaiter().GetResult()
        $stderr = $stderrTask.GetAwaiter().GetResult()
        if ($process.ExitCode -ne 0 -or -not [string]::IsNullOrWhiteSpace($stderr)) {
            throw 'PYTHON_EXECUTABLE_INVALID'
        }
        return Assert-SsaPythonProbeResult -Output $stdout -ExpectedPath $PythonPath `
            -AllowLogicalPathDifference $AllowLogicalPathDifference
    }
    finally { $process.Dispose() }
}

function Resolve-SsaPythonCandidate {
    param(
        [Parameter(Mandatory = $true)][AllowEmptyString()][string]$PythonPath,
        [Parameter(Mandatory = $true)]
        [ValidateSet('PATH', 'PARAMETER', 'SSA_PYTHON_DEVELOPMENT_NONPORTABLE')]
        [string]$Source,
        [switch]$RequireAbsolute
    )

    $normalizedInput = $PythonPath.Replace('/', '\')
    if (
        [string]::IsNullOrWhiteSpace($PythonPath) -or
        $PythonPath.Contains('"') -or
        $PythonPath.Contains([char]0) -or
        $PythonPath.IndexOfAny([char[]]'*?[]') -ge 0 -or
        $PythonPath -match '[\x01-\x1f\x7f]' -or
        $PythonPath -match '^[A-Za-z][A-Za-z0-9+.-]*://' -or
        $normalizedInput.StartsWith('\')
    ) {
        throw 'PYTHON_PATH_INVALID'
    }
    if ($RequireAbsolute -and $normalizedInput -notmatch '^[A-Za-z]:\\') {
        throw 'PYTHON_PATH_ABSOLUTE_REQUIRED'
    }
    if ([IO.Path]::IsPathRooted($PythonPath)) {
        try { $resolved = [IO.Path]::GetFullPath($PythonPath) }
        catch { throw 'PYTHON_PATH_INVALID' }
    }
    else {
        try {
            $command = Get-Command -Name $PythonPath -CommandType Application `
                -ErrorAction Stop | Select-Object -First 1
        }
        catch { throw 'PYTHON_PATH_NOT_FOUND' }
        try { $resolved = [IO.Path]::GetFullPath([string]$command.Source) }
        catch { throw 'PYTHON_PATH_INVALID' }
    }
    $normalizedResolved = $resolved.Replace('/', '\')
    if ($normalizedResolved -notmatch '^[A-Za-z]:\\') {
        throw 'PYTHON_PATH_NETWORK_OR_DEVICE_PROHIBITED'
    }
    $root = [IO.Path]::GetPathRoot($resolved)
    if ([string]::IsNullOrWhiteSpace($root)) { throw 'PYTHON_PATH_INVALID' }
    if ($resolved.Substring($root.Length).Contains(':')) {
        throw 'PYTHON_PATH_ALTERNATE_DATA_STREAM'
    }
    try {
        if ([IO.DriveInfo]::new($root).DriveType -eq [IO.DriveType]::Network) {
            throw 'PYTHON_PATH_REMOTE_DRIVE_PROHIBITED'
        }
    }
    catch [ArgumentException] { throw 'PYTHON_PATH_INVALID' }
    if (-not [IO.File]::Exists($resolved)) { throw 'PYTHON_PATH_NOT_FOUND' }
    $executable = Get-Item -LiteralPath $resolved -Force
    if ($executable -isnot [IO.FileInfo]) { throw 'PYTHON_EXECUTABLE_INVALID' }
    if (-not $executable.Name.Equals('python.exe', [StringComparison]::OrdinalIgnoreCase)) {
        throw 'PYTHON_EXECUTABLE_NAME_INVALID'
    }
    if (($executable.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw 'PYTHON_PATH_REPARSE_POINT'
    }

    $verifiedCodexPath = Get-SsaVerifiedCodexPythonPath
    $isVerifiedCodexRuntime = $resolved.Equals(
        $verifiedCodexPath,
        [StringComparison]::OrdinalIgnoreCase
    )
    if (
        $isVerifiedCodexRuntime -and
        $Source -cne 'SSA_PYTHON_DEVELOPMENT_NONPORTABLE'
    ) {
        throw 'PYTHON_CODEX_RUNTIME_REQUIRES_SSA_PYTHON'
    }
    $allowReparseAncestor = (
        $isVerifiedCodexRuntime -and
        $Source -ceq 'SSA_PYTHON_DEVELOPMENT_NONPORTABLE'
    )
    $candidate = [IO.Directory]::GetParent($resolved)
    while ($null -ne $candidate) {
        if (Test-Path -LiteralPath $candidate.FullName) {
            $item = Get-Item -LiteralPath $candidate.FullName -Force
            if (
                ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -and
                -not $allowReparseAncestor
            ) {
                throw 'PYTHON_PATH_REPARSE_POINT'
            }
        }
        $candidate = $candidate.Parent
    }
    $launchPath = Get-SsaFinalExecutablePath -Path $resolved
    $probe = Invoke-SsaPythonVersionProbe -PythonPath $launchPath `
        -AllowLogicalPathDifference $false
    [void]$probe
    return [PSCustomObject]@{
        IsVerifiedCodexRuntime = $isVerifiedCodexRuntime
        OwnershipPaths = [string[]]@($launchPath)
        Path = $launchPath
        RequestedPath = $resolved
        Source = $Source
    }
}

function Select-SsaPythonRuntime {
    param(
        [AllowNull()][AllowEmptyString()][string]$PythonPath,
        [Parameter(Mandatory = $true)][bool]$PythonPathWasBound
    )

    if ($PythonPathWasBound) {
        return Resolve-SsaPythonCandidate -PythonPath $PythonPath -Source 'PARAMETER'
    }
    $developmentPath = [Environment]::GetEnvironmentVariable('SSA_PYTHON')
    try { return Resolve-SsaPythonCandidate -PythonPath 'python' -Source 'PATH' }
    catch {
        if ($null -eq $developmentPath) { throw }
    }
    return Resolve-SsaPythonCandidate -PythonPath $developmentPath `
        -Source 'SSA_PYTHON_DEVELOPMENT_NONPORTABLE' -RequireAbsolute
}

function Write-SsaPythonRuntimeNotice {
    param([Parameter(Mandatory = $true)]$Runtime)

    if ($Runtime.Source -cne 'SSA_PYTHON_DEVELOPMENT_NONPORTABLE') { return }
    if ($Runtime.IsVerifiedCodexRuntime) {
        [Console]::Error.WriteLine(
            'DEVELOPMENT / NONPORTABLE: SSA_PYTHON selected the verified ' +
            'Codex-bundled Python 3.12 runtime. This configuration is ' +
            'development-only and is not a portable release.'
        )
        return
    }
    [Console]::Error.WriteLine(
        'DEVELOPMENT / NONPORTABLE: SSA_PYTHON selected an explicit local ' +
        'Python 3.12 runtime. This configuration is development-only and ' +
        'is not a portable release.'
    )
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
        '-s', '-E',
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
        [Parameter(Mandatory = $true)][string[]]$PythonPath,
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
    $matchesExpectedExecutable = $false
    foreach ($expectedExecutable in $PythonPath) {
        if ($actualExecutable.Equals(
            [IO.Path]::GetFullPath($expectedExecutable),
            [StringComparison]::OrdinalIgnoreCase
        )) {
            $matchesExpectedExecutable = $true
            break
        }
    }
    if (-not $matchesExpectedExecutable) {
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
