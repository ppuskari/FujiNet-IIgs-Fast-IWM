#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$DevRoot = 'C:\AppleIIgsDev_02',
    [switch]$OpenOutputFolder
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0

$thisScript = $MyInvocation.MyCommand.Path
if ([string]::IsNullOrWhiteSpace($thisScript)) {
    throw 'Unable to determine build script path.'
}

$scriptRoot = Split-Path -Parent $thisScript
$repoRoot = Split-Path -Parent $scriptRoot
$patchScript = Join-Path $repoRoot 'tools\patch_spbench_p01b3.py'
$baseBuilder = Join-Path $scriptRoot 'Build-SPBench-P01B.ps1'

if (-not (Test-Path -LiteralPath $patchScript -PathType Leaf)) {
    throw ('Missing P0.1B3 patch script: ' + $patchScript)
}
if (-not (Test-Path -LiteralPath $baseBuilder -PathType Leaf)) {
    throw ('Missing P0.1B builder: ' + $baseBuilder)
}

$pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
if ($null -eq $pythonCommand) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
}
if ($null -eq $pythonCommand) {
    throw 'Python is not available on PATH.'
}

Write-Host 'SPBENCH P0.1B3 build'
Write-Host ('Repository: ' + $repoRoot)
Write-Host ('Dev root:   ' + $DevRoot)
Write-Host ''
Write-Host '==== Apply standard SmartPort B3 patch ====' -ForegroundColor Cyan

Push-Location $repoRoot
try {
    & $pythonCommand.Source $patchScript
    $patchExit = $LASTEXITCODE
}
finally {
    Pop-Location
}

if ($patchExit -ne 0) {
    throw ('P0.1B3 source patch failed with exit code ' + $patchExit)
}

Write-Host ''
Write-Host '==== Build with validated P0.1B toolchain ====' -ForegroundColor Cyan

$childArgs = @(
    '-NoProfile',
    '-ExecutionPolicy', 'Bypass',
    '-File', $baseBuilder,
    '-DevRoot', $DevRoot
)

& powershell.exe @childArgs
$buildExit = $LASTEXITCODE
if ($buildExit -ne 0) {
    throw ('P0.1B base builder failed with exit code ' + $buildExit)
}

$releaseRoot = Join-Path $repoRoot 'build\spbench-p0.1b\release'
$sourceImage = Join-Path $releaseRoot 'SPBENCH-P0.1B.po'
$b3Image = Join-Path $releaseRoot 'SPBENCH-P0.1B3.po'

if (-not (Test-Path -LiteralPath $sourceImage -PathType Leaf)) {
    throw ('Expected image was not produced: ' + $sourceImage)
}

Copy-Item -LiteralPath $sourceImage -Destination $b3Image -Force

$b3Hash = (
    Get-FileHash -LiteralPath $b3Image -Algorithm SHA256
).Hash.ToLowerInvariant()

Write-Host ''
Write-Host 'P0.1B3 BUILD COMPLETE' -ForegroundColor Green
Write-Host ('Image:  ' + $b3Image)
Write-Host ('SHA256: ' + $b3Hash)

if ($OpenOutputFolder) {
    Start-Process explorer.exe -ArgumentList $releaseRoot
}
