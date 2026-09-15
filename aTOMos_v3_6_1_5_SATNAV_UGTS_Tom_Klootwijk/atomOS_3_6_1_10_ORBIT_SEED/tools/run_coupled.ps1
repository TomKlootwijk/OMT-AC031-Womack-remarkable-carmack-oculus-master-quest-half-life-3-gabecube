param(
    [ValidateSet('cpu','cuda')][string]$Backend = 'cpu',
    [string]$InputFile,
    [string]$OutputDirectory,
    [string]$Python = 'python'
)
$ErrorActionPreference = 'Stop'
$releaseDirectory = Split-Path -Parent $PSScriptRoot
if (-not $InputFile) { $InputFile = Join-Path $releaseDirectory 'examples\coupled\model.json' }
if (-not $OutputDirectory) { $OutputDirectory = Join-Path $releaseDirectory ('results\coupled_local_' + (Get-Date -Format 'yyyyMMdd_HHmmss_fff')) }
$nativeBinary = Join-Path $releaseDirectory ('bin\windows\' + $Backend + '\coupled_kernel.exe')
& $Python (Join-Path $PSScriptRoot 'coupled.py') --input $InputFile --out $OutputDirectory --binary $nativeBinary --backend $Backend
if ($LASTEXITCODE -ne 0) { throw "Coupled execution or replay failed (exit $LASTEXITCODE)" }
Write-Output $OutputDirectory
