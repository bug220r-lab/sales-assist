# SYNTHETIC-SALES-ASSIST-AUTHORED-M5
# Explicit draft-only entrypoint; does not alter the normal daily launcher.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ConfigFile,
    [string]$PythonPath,
    [switch]$CheckOnly
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'lifecycle-common.ps1')
try {
    $runtime = Select-SsaPythonRuntime -PythonPath $PythonPath `
        -PythonPathWasBound ($PSBoundParameters.ContainsKey('PythonPath'))
    $installation = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
    & $runtime.Path -B -I (Join-Path $installation 'tools\release_support.py') `
        verify --install-root $installation
    if ($LASTEXITCODE -ne 0) { throw 'RELEASE_PAYLOAD_VERIFICATION_FAILED' }
    $arguments = @('-B', '-s', '-E', '-m', 'doi_draft_transfer', '--config', $ConfigFile)
    if ($CheckOnly) { $arguments += '--check' }
    Push-Location (Join-Path $installation 'src')
    try {
        & $runtime.Path @arguments
        $result = $LASTEXITCODE
    }
    finally { Pop-Location }
    exit $result
}
catch {
    Write-Error -ErrorId 'SSA_DRAFT_START_FAILED' -Message 'DRAFT_LAUNCH_FAILED'
    exit 1
}
