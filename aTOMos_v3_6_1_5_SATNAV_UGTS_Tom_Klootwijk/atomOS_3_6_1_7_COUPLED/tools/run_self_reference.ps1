param(
    [ValidateSet('cpu','cuda')][string]$Backend = 'cpu',
    [string]$InputFile,
    [string]$OutputDirectory,
    [string]$Python = 'python'
)
$ErrorActionPreference = 'Stop'
$releaseDirectory = Split-Path -Parent $PSScriptRoot
if (-not $InputFile) { $InputFile = Join-Path $releaseDirectory 'examples\self_reference\equations.json' }
if (-not $OutputDirectory) { $OutputDirectory = Join-Path $releaseDirectory ('results\selfref_local_' + (Get-Date -Format 'yyyyMMdd_HHmmss_fff')) }
$nativeBinary = Join-Path $releaseDirectory ('bin\windows\' + $Backend + '\self_reference.exe')
& $Python (Join-Path $PSScriptRoot 'self_reference.py') --input $InputFile --out $OutputDirectory --binary $nativeBinary --backend $Backend
if ($LASTEXITCODE -ne 0) { throw "Self-reference execution or replay failed (exit $LASTEXITCODE)" }
Write-Output $OutputDirectory
