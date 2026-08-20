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
$patchA3 = Join-Path $repoRoot 'tools\patch_iwmprobe_p02a3.py'
$patchA4 = Join-Path $repoRoot 'tools\patch_iwmprobe_p02a4.py'
$baseBuilder = Join-Path $scriptRoot 'Build-IWMProbe-P02A.ps1'

foreach ($required in @($patchA3, $patchA4, $baseBuilder)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw ('Missing required file: ' + $required)
    }
}

$pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
if ($null -eq $pythonCommand) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
}
if ($null -eq $pythonCommand) {
    throw 'Python is not available on PATH.'
}

Write-Host 'IWMPROBE P0.2A4 build'
Write-Host ('Repository: ' + $repoRoot)
Write-Host ''

Push-Location $repoRoot
try {
    & $pythonCommand.Source $patchA3
    $patchExit = $LASTEXITCODE
    if ($patchExit -ne 0) {
        throw ('P0.2A3 patch failed with exit code ' + $patchExit)
    }

    & $pythonCommand.Source $patchA4
    $patchExit = $LASTEXITCODE
    if ($patchExit -ne 0) {
        throw ('P0.2A4 patch failed with exit code ' + $patchExit)
    }
}
finally {
    Pop-Location
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
$newImage = Join-Path $releaseRoot 'IWMPROBE-P0.2A4.po'

if (-not (Test-Path -LiteralPath $oldImage -PathType Leaf)) {
    throw ('Expected image not found: ' + $oldImage)
}
Copy-Item -LiteralPath $oldImage -Destination $newImage -Force

$hash = Get-FileHash -LiteralPath $newImage -Algorithm SHA256
Write-Host ''
Write-Host 'IWMPROBE P0.2A4 BUILD COMPLETE' -ForegroundColor Green
Write-Host ('Image:  ' + $newImage)
Write-Host ('SHA256: ' + $hash.Hash.ToLowerInvariant())

if ($OpenOutputFolder) {
    Start-Process explorer.exe -ArgumentList $releaseRoot
}
