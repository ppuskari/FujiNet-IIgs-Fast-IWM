#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$DevRoot = 'C:\AppleIIgsDev_02',
    [string]$ProjectRoot = 'C:\AppleIIgsDev_02\FujiNet-IIgs-Fast-IWM',
    [string]$PinnedFujiNetCommit = 'b0a9483463c93ab61279d265467159c0d27c9f82'
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

$Branch = 'exp/fastiwm-p0.2c4-delayed-autosend'
$ProjectWork = Join-Path $DevRoot '_FastIWM_P02C5_Project'
$FirmwareRepo = Join-Path $ProjectRoot 'work\fujinet-firmware'
$FirmwareWork = Join-Path $DevRoot '_FastIWM_P02C5_Firmware'
$FinalRelease = Join-Path $ProjectRoot 'build\fastiwm-p0.2c5-firmware'

Write-Host ''
Write-Host '=== Fast-IWM P0.2C5 firmware-only build ===' -ForegroundColor Cyan
Write-Host 'Explicit spifast SPI-bus acquisition before interrupt suppression.'
Write-Host 'Keep using FASTPROBE-P0.2C.po.'
Write-Host ''

& git.exe -C $ProjectRoot fetch origin $Branch
if ($LASTEXITCODE -ne 0) { throw 'Project branch fetch failed.' }

if (Test-Path -LiteralPath $ProjectWork) {
    & git.exe -C $ProjectRoot worktree remove --force $ProjectWork
    if ($LASTEXITCODE -ne 0 -and (Test-Path -LiteralPath $ProjectWork)) {
        Remove-Item -LiteralPath $ProjectWork -Recurse -Force
    }
    & git.exe -C $ProjectRoot worktree prune
}

& git.exe -C $ProjectRoot worktree add --detach $ProjectWork ('origin/' + $Branch)
if ($LASTEXITCODE -ne 0) { throw 'Project worktree add failed.' }

& git.exe -C $FirmwareRepo cat-file -e ($PinnedFujiNetCommit + '^{commit}')
if ($LASTEXITCODE -ne 0) { throw 'Pinned FujiNet commit missing.' }

if (Test-Path -LiteralPath $FirmwareWork) {
    & git.exe -C $FirmwareRepo worktree remove --force $FirmwareWork
    if ($LASTEXITCODE -ne 0 -and (Test-Path -LiteralPath $FirmwareWork)) {
        Remove-Item -LiteralPath $FirmwareWork -Recurse -Force
    }
    & git.exe -C $FirmwareRepo worktree prune
}

& git.exe -C $FirmwareRepo worktree add --detach $FirmwareWork $PinnedFujiNetCommit
if ($LASTEXITCODE -ne 0) { throw 'FujiNet worktree add failed.' }

try {
    $builder = Join-Path $ProjectWork 'scripts\Build-FujiNet-P02C5.ps1'
    & powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File $builder `
        -DevRoot $DevRoot `
        -FirmwareRoot $FirmwareWork
    if ($LASTEXITCODE -ne 0) {
        throw ('P0.2C5 firmware build failed with exit code ' + $LASTEXITCODE)
    }

    $WorkRelease = Join-Path $ProjectWork 'build\fastiwm-p0.2c5-firmware'
    if (-not (Test-Path -LiteralPath $WorkRelease -PathType Container)) {
        throw ('P0.2C5 release missing: ' + $WorkRelease)
    }

    if (Test-Path -LiteralPath $FinalRelease) {
        Remove-Item -LiteralPath $FinalRelease -Recurse -Force
    }
    Copy-Item -LiteralPath $WorkRelease -Destination $FinalRelease -Recurse -Force

    Write-Host ''
    Write-Host '=== P0.2C5 FINAL PACKAGE READY ===' -ForegroundColor Green
    Write-Host ('Firmware: ' + (Join-Path $FinalRelease 'fujinet-p0.2c5-firmware.bin'))
    Write-Host 'Host: KEEP FASTPROBE-P0.2C.po' -ForegroundColor Green
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
