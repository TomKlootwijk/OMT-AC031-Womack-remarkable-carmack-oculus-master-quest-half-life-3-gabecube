param(
    [string]$BuildDirectory = 'C:/aTOMosBuild/r15cuda',
    [string]$CudaToolset = '12.8',
    [int]$Parallel = 8
)
$ErrorActionPreference = 'Stop'
$r15Source = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$r15Workspace = (Resolve-Path (Join-Path $r15Source '..')).Path
$r15S2 = Join-Path $r15Workspace 'tmp/s2_comparison/s2geometry'
$r15Revision = '079611b654ad89afd9c3c3a1796d64bdd6a6b340'
if (-not (Test-Path -LiteralPath $r15S2)) {
    git clone https://github.com/google/s2geometry.git $r15S2
    if ($LASTEXITCODE -ne 0) { throw 'S2 clone failed' }
    git -C $r15S2 checkout --detach $r15Revision
    if ($LASTEXITCODE -ne 0) { throw 'S2 revision selection failed' }
}
$r15Actual = git -C $r15S2 rev-parse HEAD
if ($LASTEXITCODE -ne 0 -or $r15Actual.Trim() -ne $r15Revision) {
    throw 'Existing S2 checkout does not match the pinned reference; select a separate correct checkout.'
}
cmake -S $r15Source -B $BuildDirectory -G 'Visual Studio 17 2022' -A x64 -T "cuda=$CudaToolset" -DATOMOS_CUDA=ON -DATOMOS_S2_SOURCE="$r15S2"
if ($LASTEXITCODE -ne 0) { throw 'Native configuration failed' }
cmake --build $BuildDirectory --config Release --parallel $Parallel
if ($LASTEXITCODE -ne 0) { throw 'Native build failed' }
ctest --test-dir $BuildDirectory -C Release --output-on-failure
if ($LASTEXITCODE -ne 0) { throw 'Native correctness checks failed' }
