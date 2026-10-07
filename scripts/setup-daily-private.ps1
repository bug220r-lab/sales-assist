# SYNTHETIC-SALES-ASSIST-AUTHORED-M8
# Create a private launch configuration for one verified local daily package.
# Values must come from the operator's separately reviewed, approved policy.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][ValidateNotNullOrEmpty()][string]$PackageRoot,
    [Parameter(Mandatory=$true)][ValidateNotNullOrEmpty()][string]$ConfirmationPath,
    [Parameter(Mandatory=$true)][ValidatePattern('^[a-f0-9]{64}$')][string]$ApprovedSha256,
    [Parameter(Mandatory=$true)][ValidateRange(1, 10)][int]$ExpectedDecisionCount
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
function Resolve-DailySetupLocalPath([string]$Value, [switch]$CheckExisting) {
    # Validate caller-supplied paths before probing a file or invoking package code.
    if ($Value -cnotmatch '^[A-Za-z]:[\\/]' -or
        $Value.Substring(2).Contains(':') -or
        $Value -match '[\x00-\x1f"]' -or
        $Value -match '(^|[\\/])\.\.?([\\/]|$)') {
        throw 'DAILY_SETUP_ABSOLUTE_LOCAL_PATH_REQUIRED'
    }
    $resolved = [IO.Path]::GetFullPath($Value)
    if ($resolved -match '(?i)(^|[\\/])(OneDrive(?: - [^\\/]+)?|Dropbox|Google Drive|iCloudDrive)([\\/]|$)') {
        throw 'DAILY_SETUP_SYNCHRONIZED_PATH_PROHIBITED'
    }
    foreach ($name in @('OneDrive', 'OneDriveCommercial', 'OneDriveConsumer')) {
        $syncRoot = [Environment]::GetEnvironmentVariable($name)
        if (-not [string]::IsNullOrWhiteSpace($syncRoot)) {
            $prefix = [IO.Path]::GetFullPath($syncRoot).TrimEnd('\')
            if ($resolved.Equals($prefix, [StringComparison]::OrdinalIgnoreCase) -or
                $resolved.StartsWith($prefix + '\', [StringComparison]::OrdinalIgnoreCase)) {
                throw 'DAILY_SETUP_SYNCHRONIZED_PATH_PROHIBITED'
            }
        }
    }
    if (-not $CheckExisting) { return $resolved }
    if ([IO.DriveInfo]::new([IO.Path]::GetPathRoot($resolved)).DriveType -ne [IO.DriveType]::Fixed) {
        throw 'DAILY_SETUP_FIXED_LOCAL_DISK_REQUIRED'
    }
    # Walk outward from the drive root; never inspect a child through a reparse parent.
    $candidate = [IO.Path]::GetPathRoot($resolved)
    $parts = @('') + $resolved.Substring($candidate.Length).Split([char[]]@('\', '/'),
        [StringSplitOptions]::RemoveEmptyEntries)
    foreach ($part in $parts) {
        if ($part.Length -gt 0) { $candidate = [IO.Path]::Combine($candidate, $part) }
        try {
            $attributes = [IO.File]::GetAttributes($candidate)
            if (($attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw 'DAILY_SETUP_REPARSE_POINT_PROHIBITED'
            }
        } catch [IO.FileNotFoundException] { }
        catch [IO.DirectoryNotFoundException] { }
    }
    return $resolved
}
$PackageRoot = Resolve-DailySetupLocalPath $PackageRoot
$ConfirmationPath = Resolve-DailySetupLocalPath $ConfirmationPath
$packagePrefix = $PackageRoot.TrimEnd('\') + '\'
if ($ConfirmationPath.StartsWith($packagePrefix, [StringComparison]::OrdinalIgnoreCase) -or
    $ConfirmationPath.Equals($PackageRoot, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'DAILY_SETUP_POLICY_MUST_BE_EXTERNAL'
}
$PackageRoot = Resolve-DailySetupLocalPath $PackageRoot -CheckExisting
$ConfirmationPath = Resolve-DailySetupLocalPath $ConfirmationPath -CheckExisting
$python = Resolve-DailySetupLocalPath (Join-Path $PackageRoot 'python\python.exe') -CheckExisting
$support = Resolve-DailySetupLocalPath (Join-Path $PackageRoot 'tools\release_support.py') -CheckExisting
$dailyPolicySupport = Resolve-DailySetupLocalPath (Join-Path $PackageRoot 'tools\daily_policy.py') -CheckExisting
if (!(Test-Path -LiteralPath $ConfirmationPath -PathType Leaf)) {
    throw 'Existing approved confirmation file is missing. No setup performed.'
}
if ((Get-FileHash -LiteralPath $ConfirmationPath -Algorithm SHA256).Hash.ToLowerInvariant() -cne $ApprovedSha256) {
    throw 'Confirmation file differs from the approved hash. No setup performed.'
}
if (!(Test-Path -LiteralPath $python -PathType Leaf)) {
    throw 'Extract the complete package to a short local path first.'
}
& $python -B -I $support verify --install-root $PackageRoot
if ($LASTEXITCODE -ne 0) { throw 'Package verification failed. No setup performed.' }
$selection = @(& $python -B -I $support data-root --install-root $PackageRoot)
if ($LASTEXITCODE -ne 0) { throw 'Data selection unavailable. No setup performed.' }
$dataDir = Resolve-DailySetupLocalPath ((($selection -join "`n") | ConvertFrom-Json).data_dir) -CheckExisting
$configPath = Resolve-DailySetupLocalPath (Join-Path $dataDir 'doi-private-launch.json') -CheckExisting
$receiptPath = Resolve-DailySetupLocalPath (Join-Path $dataDir 'runtime\service.json') -CheckExisting
if (Test-Path -LiteralPath $configPath) {
    throw 'Private launch configuration already exists. This recipe never overwrites it.'
}
if (Test-Path -LiteralPath $receiptPath) {
    throw 'A runtime receipt already exists in this data selection. Review that state before private setup.'
}
$configuration = @{
    schema = 'ssa-doi-private-launch/v1'
    confirmation_path = $ConfirmationPath
    confirmation_sha256 = $ApprovedSha256
    expected_decision_count = $ExpectedDecisionCount
}
[void](New-Item -ItemType Directory -Path $dataDir -Force)
$bytes = [Text.UTF8Encoding]::new($false).GetBytes(($configuration | ConvertTo-Json))
$stream = [IO.File]::Open($configPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
try { $stream.Write($bytes, 0, $bytes.Length); $stream.Flush($true) }
finally { $stream.Dispose() }
$verified = @(& $python -B -I $dailyPolicySupport check --data-dir $dataDir)
if ($LASTEXITCODE -ne 0) {
    throw 'Private configuration was created but validation failed. START remains blocked; inspect the bounded error above.'
}
Write-Host 'Private launch configuration verified. The existing confirmation file was not copied or changed.'
Write-Host 'Confirmations apply only to their matching capture. Launch START.cmd manually after review.'
