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
$patchScript = Join-Path $repoRoot 'tools\patch_iwmprobe_p02a5.py'
$baseBuilder = Join-Path $scriptRoot 'Build-IWMProbe-P02A.ps1'

if (-not (Test-Path -LiteralPath $patchScript -PathType Leaf)) {
    throw ('Missing patch script: ' + $patchScript)
}
if (-not (Test-Path -LiteralPath $baseBuilder -PathType Leaf)) {
    throw ('Missing base builder: ' + $baseBuilder)
}

$pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
if ($null -eq $pythonCommand) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
}
if ($null -eq $pythonCommand) {
    throw 'Python is not available on PATH.'
}

Write-Host 'IWMPROBE P0.2A5 build'
Write-Host ('Repository: ' + $repoRoot)
Write-Host ''

Push-Location $repoRoot
try {
    & $pythonCommand.Source $patchScript
    $patchExit = $LASTEXITCODE
}
finally {
    Pop-Location
}
if ($patchExit -ne 0) {
    throw ('P0.2A5 patch failed with exit code ' + $patchExit)
}

$childArgs = @(
    '-NoProfile',
    '-ExecutionPolicy', 'Bypass',
    '-File', $baseBuilder,
    '-DevRoot', $DevRoot
)
& powershell.exe @childArgs
$buildExit = $LASTEXITCODE
if ($buildExit -ne 0) {
    throw ('P0.2A base builder failed with exit code ' + $buildExit)
}

$releaseRoot = Join-Path $repoRoot 'build\iwmprobe-p0.2a\release'
$oldImage = Join-Path $releaseRoot 'IWMPROBE-P0.2A.po'
$newImage = Join-Path $releaseRoot 'IWMPROBE-P0.2A5.po'

if (-not (Test-Path -LiteralPath $oldImage -PathType Leaf)) {
    throw ('Expected image not found: ' + $oldImage)
}
Copy-Item -LiteralPath $oldImage -Destination $newImage -Force

$hash = Get-FileHash -LiteralPath $newImage -Algorithm SHA256
Write-Host ''
Write-Host 'IWMPROBE P0.2A5 BUILD COMPLETE' -ForegroundColor Green
Write-Host ('Image:  ' + $newImage)
Write-Host ('SHA256: ' + $hash.Hash.ToLowerInvariant())

if ($OpenOutputFolder) {
    Start-Process explorer.exe -ArgumentList $releaseRoot
}
