param(
    [string]$BuildDirectory = 'C:/aTOMosBuild/r18cuda',
    [string]$CudaToolset = '12.8',
    [int]$Parallel = 8
)
$ErrorActionPreference = 'Stop'
$r17Source = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$r17Workspace = (Resolve-Path (Join-Path $r17Source '..')).Path
$r17S2 = Join-Path $r17Workspace 'tmp/s2_comparison/s2geometry'
$r17Revision = '079611b654ad89afd9c3c3a1796d64bdd6a6b340'
if (-not (Test-Path -LiteralPath $r17S2)) {
    git clone https://github.com/google/s2geometry.git $r17S2
    if ($LASTEXITCODE -ne 0) { throw 'S2 clone failed' }
    git -C $r17S2 checkout --detach $r17Revision
    if ($LASTEXITCODE -ne 0) { throw 'S2 revision selection failed' }
}
$r17Actual = git -C $r17S2 rev-parse HEAD
if ($LASTEXITCODE -ne 0 -or $r17Actual.Trim() -ne $r17Revision) {
    throw 'Existing S2 checkout does not match the pinned reference; select a separate correct checkout.'
}
cmake -S $r17Source -B $BuildDirectory -G 'Visual Studio 17 2022' -A x64 -T "cuda=$CudaToolset" -DATOMOS_CUDA=ON -DATOMOS_S2_SOURCE="$r17S2"
if ($LASTEXITCODE -ne 0) { throw 'Native configuration failed' }
cmake --build $BuildDirectory --config Release --parallel $Parallel
if ($LASTEXITCODE -ne 0) { throw 'Native build failed' }
ctest --test-dir $BuildDirectory -C Release --output-on-failure
if ($LASTEXITCODE -ne 0) { throw 'Native correctness checks failed' }
