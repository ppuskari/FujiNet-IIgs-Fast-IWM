#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$DevRoot = 'C:\AppleIIgsDev_02'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0

$thisScript = $MyInvocation.MyCommand.Path
if ([string]::IsNullOrWhiteSpace($thisScript)) {
    throw 'Unable to determine build script path.'
}

$scriptRoot = Split-Path -Parent $thisScript
$repoRoot = Split-Path -Parent $scriptRoot
$sourceRoot = Join-Path $repoRoot 'iigs\fastprobe\src'
$releaseRoot = Join-Path $repoRoot 'build\fastprobe-p0.2b3'

$python = Get-Command python.exe -ErrorAction SilentlyContinue
if ($null -eq $python) {
    $python = Get-Command python -ErrorAction SilentlyContinue
}
if ($null -eq $python) {
    throw 'Python is not available on PATH.'
}

$patchB2 = Join-Path $repoRoot 'tools\patch_fastprobe_p02b2.py'
$patchB3 = Join-Path $repoRoot 'tools\patch_fastprobe_p02b3.py'

foreach ($required in @($patchB2, $patchB3)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw ('Missing patch script: ' + $required)
    }
}

& $python.Source $patchB2 --project-root $repoRoot
if ($LASTEXITCODE -ne 0) {
    throw 'P0.2B2 host patch failed.'
}

& $python.Source $patchB3 --project-root $repoRoot
if ($LASTEXITCODE -ne 0) {
    throw 'P0.2B3 host patch failed.'
}

$baseBuilder = Join-Path $repoRoot 'scripts\Build-FastProbe-P02B.ps1'
& powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File $baseBuilder -DevRoot $DevRoot
if ($LASTEXITCODE -ne 0) {
    throw 'FASTPROBE base builder failed.'
}

$baseRelease = Join-Path $repoRoot 'build\fastprobe-p0.2b\release'
if (Test-Path -LiteralPath $releaseRoot) {
    Remove-Item -LiteralPath $releaseRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $releaseRoot -Force | Out-Null

Copy-Item -LiteralPath (Join-Path $baseRelease 'FASTPROBE-P0.2B.po') `
    -Destination (Join-Path $releaseRoot 'FASTPROBE-P0.2B3.po') -Force
Copy-Item -LiteralPath (Join-Path $baseRelease 'FASTPROBE#B30000') `
    -Destination (Join-Path $releaseRoot 'FASTPROBE-P0.2B3#B30000') -Force

foreach ($optional in @('FASTPROBE_Output.txt','FASTPROBE-P0.2B.catalog.txt')) {
    $candidate = Join-Path $baseRelease $optional
    if (Test-Path -LiteralPath $candidate -PathType Leaf) {
        Copy-Item -LiteralPath $candidate -Destination $releaseRoot -Force
    }
}

$hashLines = @()
Get-ChildItem -LiteralPath $releaseRoot -File |
    Sort-Object Name |
    ForEach-Object {
        $hash = Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256
        $hashLines += ($hash.Hash.ToLowerInvariant() + '  ' + $_.Name)
    }
$hashLines | Set-Content -LiteralPath (Join-Path $releaseRoot 'SHA256SUMS.txt') -Encoding ASCII

Write-Host ''
Write-Host 'FASTPROBE P0.2B3 BUILD COMPLETE' -ForegroundColor Green
Write-Host ('Image: ' + (Join-Path $releaseRoot 'FASTPROBE-P0.2B3.po'))
Write-Host 'FujiNet firmware: keep existing P0.2B2 application firmware.'
