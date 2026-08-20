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
$releaseRoot = Join-Path $repoRoot 'build\fastprobe-p0.2b4'

$python = Get-Command python.exe -ErrorAction SilentlyContinue
if ($null -eq $python) {
    $python = Get-Command python -ErrorAction SilentlyContinue
}
if ($null -eq $python) {
    throw 'Python is not available on PATH.'
}

$patchB4 = Join-Path $repoRoot 'tools\patch_fastprobe_p02b4.py'
if (-not (Test-Path -LiteralPath $patchB4 -PathType Leaf)) {
    throw ('Missing P0.2B4 patch script: ' + $patchB4)
}

# P0.2B4 owns the cumulative patch chain. It establishes B2 and B3
# prerequisites itself before applying B4. Do not invoke B2/B3 again here.
& $python.Source $patchB4 --project-root $repoRoot
if ($LASTEXITCODE -ne 0) {
    throw 'P0.2B4 host patch failed.'
}

$baseBuilder = Join-Path $repoRoot 'scripts\Build-FastProbe-P02B.ps1'
& powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File $baseBuilder -DevRoot $DevRoot
if ($LASTEXITCODE -ne 0) {
    throw 'FASTPROBE base builder failed.'
}

$baseRelease = Join-Path $repoRoot 'build\fastprobe-p0.2b\release'
$basePo = Join-Path $baseRelease 'FASTPROBE-P0.2B.po'
$baseS16 = Join-Path $baseRelease 'FASTPROBE#B30000'

if (-not (Test-Path -LiteralPath $basePo -PathType Leaf)) {
    throw ('Base PO missing after build: ' + $basePo)
}
if (-not (Test-Path -LiteralPath $baseS16 -PathType Leaf)) {
    throw ('Base S16 missing after build: ' + $baseS16)
}

if (Test-Path -LiteralPath $releaseRoot) {
    Remove-Item -LiteralPath $releaseRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $releaseRoot -Force | Out-Null

Copy-Item -LiteralPath $basePo `
    -Destination (Join-Path $releaseRoot 'FASTPROBE-P0.2B4.po') -Force
Copy-Item -LiteralPath $baseS16 `
    -Destination (Join-Path $releaseRoot 'FASTPROBE-P0.2B4#B30000') -Force

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
$hashLines | Set-Content `
    -LiteralPath (Join-Path $releaseRoot 'SHA256SUMS.txt') `
    -Encoding ASCII

Write-Host ''
Write-Host 'FASTPROBE P0.2B4 BUILD COMPLETE' -ForegroundColor Green
Write-Host ('Image: ' + (Join-Path $releaseRoot 'FASTPROBE-P0.2B4.po'))
Write-Host 'FujiNet firmware: keep existing P0.2B2 application firmware.'
