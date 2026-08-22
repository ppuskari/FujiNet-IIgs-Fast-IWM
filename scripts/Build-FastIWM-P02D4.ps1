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
if ([string]::IsNullOrWhiteSpace($FirmwareRoot)) {
    $FirmwareRoot = Join-Path $repoRoot 'work\fujinet-firmware'
}

$pairBuilder = Join-Path $scriptRoot 'Build-FastIWM-P02C9.ps1'
$hostOverlay = Join-Path $repoRoot `
    'tools\patch_spbench_fastiwm_p02d4_spi_wait.py'
$firmwareOverlay = Join-Path $repoRoot `
    'tools\patch_fujinet_fastiwm_p02d4_spi_wait.py'

$buildArgs = @(
    '-NoProfile'
    '-ExecutionPolicy', 'Bypass'
    '-File', $pairBuilder
    '-DevRoot', $DevRoot
    '-FirmwareRoot', $FirmwareRoot
    '-SourceRef', 'b3a969b8eda762d4792115b0185972782d8d8ed6'
    '-FirmwareSourceRef', 'b0a9483463c93ab61279d265467159c0d27c9f82'
    '-Experiment', 'P0.2D4'
    '-FirmwareExperiment', 'P0.2D4'
    '-HostOverlayPatch', $hostOverlay
    '-FirmwareOverlayPatch', $firmwareOverlay
)
if ($PackageExisting) {
    $buildArgs += '-PackageExisting'
}

& powershell.exe @buildArgs
if ($LASTEXITCODE -ne 0) {
    throw ('P0.2D4 matched build failed with exit code ' + $LASTEXITCODE)
}
