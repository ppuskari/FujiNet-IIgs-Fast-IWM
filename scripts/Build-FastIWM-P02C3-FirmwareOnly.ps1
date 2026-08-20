#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$DevRoot = 'C:\AppleIIgsDev_02',
    [string]$ProjectRoot = 'C:\AppleIIgsDev_02\FujiNet-IIgs-Fast-IWM',
    [string]$PinnedFujiNetCommit = 'b0a9483463c93ab61279d265467159c0d27c9f82'
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

$Branch = 'exp/fastiwm-p0.2c2-arm-hold'
$ProjectWork = Join-Path $DevRoot '_FastIWM_P02C3_Project'
$FirmwareRepo = Join-Path $ProjectRoot 'work\fujinet-firmware'
$FirmwareWork = Join-Path $DevRoot '_FastIWM_P02C3_Firmware'
$FinalRelease = Join-Path $ProjectRoot 'build\fastiwm-p0.2c3-firmware'

Write-Host ''
Write-Host '=== FujiNet P0.2C3 firmware-only diagnostic build ===' -ForegroundColor Cyan
Write-Host 'Keep using the existing FASTPROBE-P0.2C.po host image.'
Write-Host ''

if (-not (Test-Path -LiteralPath $ProjectRoot -PathType Container)) {
    throw ('Project root missing: ' + $ProjectRoot)
}
if (-not (Test-Path -LiteralPath $FirmwareRepo -PathType Container)) {
    throw ('Pinned FujiNet repository missing: ' + $FirmwareRepo)
}

& git.exe -C $ProjectRoot fetch origin $Branch
$fetchExit = $LASTEXITCODE
if ($fetchExit -ne 0) {
    throw ('git fetch failed with exit code ' + $fetchExit)
}

if (Test-Path -LiteralPath $ProjectWork) {
    & git.exe -C $ProjectRoot worktree remove --force $ProjectWork
    $removeExit = $LASTEXITCODE
    if ($removeExit -ne 0 -and (Test-Path -LiteralPath $ProjectWork)) {
        Remove-Item -LiteralPath $ProjectWork -Recurse -Force
    }
    & git.exe -C $ProjectRoot worktree prune
}

& git.exe -C $ProjectRoot worktree add --detach `
    $ProjectWork `
    ('origin/' + $Branch)
$projectExit = $LASTEXITCODE
if ($projectExit -ne 0) {
    throw ('project worktree add failed with exit code ' + $projectExit)
}

& git.exe -C $FirmwareRepo cat-file -e ($PinnedFujiNetCommit + '^{commit}')
if ($LASTEXITCODE -ne 0) {
    throw ('Pinned FujiNet commit unavailable: ' + $PinnedFujiNetCommit)
}

if (Test-Path -LiteralPath $FirmwareWork) {
    & git.exe -C $FirmwareRepo worktree remove --force $FirmwareWork
    $removeExit = $LASTEXITCODE
    if ($removeExit -ne 0 -and (Test-Path -LiteralPath $FirmwareWork)) {
        Remove-Item -LiteralPath $FirmwareWork -Recurse -Force
    }
    & git.exe -C $FirmwareRepo worktree prune
}

& git.exe -C $FirmwareRepo worktree add --detach `
    $FirmwareWork `
    $PinnedFujiNetCommit
$firmwareExit = $LASTEXITCODE
if ($firmwareExit -ne 0) {
    throw ('FujiNet worktree add failed with exit code ' + $firmwareExit)
}

try {
    $builder = Join-Path $ProjectWork 'scripts\Build-FujiNet-P02C3.ps1'
    if (-not (Test-Path -LiteralPath $builder -PathType Leaf)) {
        throw ('P0.2C3 builder missing: ' + $builder)
    }

    & powershell.exe `
        -NoProfile `
        -ExecutionPolicy Bypass `
        -File $builder `
        -DevRoot $DevRoot `
        -FirmwareRoot $FirmwareWork

    $buildExit = $LASTEXITCODE
    if ($buildExit -ne 0) {
        throw ('P0.2C3 firmware build failed with exit code ' + $buildExit)
    }

    $WorkRelease = Join-Path $ProjectWork 'build\fastiwm-p0.2c3-firmware'
    if (-not (Test-Path -LiteralPath $WorkRelease -PathType Container)) {
        throw ('P0.2C3 release directory missing: ' + $WorkRelease)
    }

    if (Test-Path -LiteralPath $FinalRelease) {
        Remove-Item -LiteralPath $FinalRelease -Recurse -Force
    }

    Copy-Item `
        -LiteralPath $WorkRelease `
        -Destination $FinalRelease `
        -Recurse `
        -Force

    $zipPath = $FinalRelease + '.zip'
    if (Test-Path -LiteralPath $zipPath) {
        Remove-Item -LiteralPath $zipPath -Force
    }

    Compress-Archive `
        -Path (Join-Path $FinalRelease '*') `
        -DestinationPath $zipPath `
        -CompressionLevel Optimal

    $zipHash = Get-FileHash -LiteralPath $zipPath -Algorithm SHA256

    Write-Host ''
    Write-Host '=== P0.2C3 FINAL PACKAGE READY ===' -ForegroundColor Green
    Write-Host ('Firmware: ' + (Join-Path $FinalRelease 'fujinet-p0.2c3-firmware.bin'))
    Write-Host ('ZIP:      ' + $zipPath)
    Write-Host ('SHA256:   ' + $zipHash.Hash.ToLowerInvariant())
    Write-Host 'Host image: KEEP FASTPROBE-P0.2C.po' -ForegroundColor Green
}
finally {
    if (Test-Path -LiteralPath $ProjectWork) {
        & git.exe -C $ProjectRoot worktree remove --force $ProjectWork
        & git.exe -C $ProjectRoot worktree prune
    }

    if (Test-Path -LiteralPath $FirmwareWork) {
        & git.exe -C $FirmwareRepo worktree remove --force $FirmwareWork
        & git.exe -C $FirmwareRepo worktree prune
    }
}
