param(
    [string]$SdkPath = "$env:LOCALAPPDATA/Android/Sdk",
    [string]$JdkPath = 'C:/Program Files/Android/Android Studio/jbr',
    [switch]$IncludeTests
)
$ErrorActionPreference = 'Stop'
$androidProject = Join-Path (Split-Path $PSScriptRoot -Parent) 'android'
if (-not (Test-Path -LiteralPath (Join-Path $SdkPath 'platforms/android-36/android.jar'))) { throw 'Android SDK platform 36 is required.' }
if (-not (Test-Path -LiteralPath (Join-Path $JdkPath 'bin/java.exe'))) { throw 'Pass -JdkPath pointing to JDK 17 or newer.' }
$oldJava = $env:JAVA_HOME
$oldAndroid = $env:ANDROID_HOME
try {
    $env:JAVA_HOME = $JdkPath
    $env:ANDROID_HOME = $SdkPath
    Push-Location -LiteralPath $androidProject
    try {
        $tasks = @('assembleDebug', 'lintDebug')
        if ($IncludeTests) { $tasks += 'assembleDebugAndroidTest' }
        & .\gradlew.bat @tasks --no-daemon --console=plain
        if ($LASTEXITCODE -ne 0) { throw "Android build failed: $LASTEXITCODE" }
        $outputDir = Join-Path (Split-Path $androidProject -Parent) 'output/android'
        New-Item -ItemType Directory -Path $outputDir -Force | Out-Null
        $outputApk = Join-Path $outputDir 'aTOMos-Radio-3.6.1.20-debug.apk'
        Copy-Item -LiteralPath (Join-Path $androidProject 'app/build/outputs/apk/debug/app-debug.apk') -Destination $outputApk -Force
        Get-FileHash -LiteralPath $outputApk -Algorithm SHA256
    } finally { Pop-Location }
} finally { $env:JAVA_HOME = $oldJava; $env:ANDROID_HOME = $oldAndroid }
