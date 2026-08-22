#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$DevRoot = 'C:\AppleIIgsDev_02',
    [string]$FirmwareRoot,
    [switch]$PackageExisting
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptRoot
$hostBuilder = Join-Path $scriptRoot 'Build-FastProbe-P02C9.ps1'
$firmwareBuilder = Join-Path $scriptRoot 'Build-FujiNet-P02C9.ps1'
$pairBuilder = Join-Path $scriptRoot 'Build-FastIWM-P02C9.ps1'
$hostOverlay = Join-Path $repoRoot `
    'tools\patch_spbench_fastiwm_p02d6_direct_ring.py'
$firmwareOverlay = Join-Path $repoRoot `
    'tools\patch_fujinet_fastiwm_p02d4_spi_wait.py'
if ([string]::IsNullOrWhiteSpace($FirmwareRoot)) {
    $FirmwareRoot = Join-Path $repoRoot 'work\fujinet-firmware'
}

if (-not $PackageExisting) {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File $hostBuilder `
        -DevRoot $DevRoot `
        -SourceRef 'b3a969b8eda762d4792115b0185972782d8d8ed6' `
        -Experiment 'P0.2D6' `
        -FirmwareExperiment 'P0.2D4' `
        -OverlayPatch $hostOverlay
    if ($LASTEXITCODE -ne 0) {
        throw ('P0.2D6 host build failed with exit code ' + $LASTEXITCODE)
    }

    # P0.2D6 deliberately reuses the proven P0.2D4 firmware. Rebuild it from
    # its pinned clean source so a fresh checkout can generate the complete
    # matched pair without relying on an old local build directory.
    & powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File $firmwareBuilder `
        -DevRoot $DevRoot `
        -FirmwareRoot $FirmwareRoot `
        -FirmwareSourceRef 'b0a9483463c93ab61279d265467159c0d27c9f82' `
        -Experiment 'P0.2D4' `
        -OverlayPatch $firmwareOverlay
    if ($LASTEXITCODE -ne 0) {
        throw ('P0.2D4 firmware build failed with exit code ' + $LASTEXITCODE)
    }
}

& powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File $pairBuilder `
    -DevRoot $DevRoot `
    -Experiment 'P0.2D6' `
    -FirmwareExperiment 'P0.2D4' `
    -PackageExisting
if ($LASTEXITCODE -ne 0) {
    throw ('P0.2D6/D4 packaging failed with exit code ' + $LASTEXITCODE)
}
