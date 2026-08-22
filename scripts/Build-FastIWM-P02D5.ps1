#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$DevRoot = 'C:\AppleIIgsDev_02',
    [switch]$PackageExisting
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptRoot
$hostBuilder = Join-Path $scriptRoot 'Build-FastProbe-P02C9.ps1'
$pairBuilder = Join-Path $scriptRoot 'Build-FastIWM-P02C9.ps1'
$hostOverlay = Join-Path $repoRoot `
    'tools\patch_spbench_fastiwm_p02d5_thunk_flags.py'

if (-not $PackageExisting) {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File $hostBuilder `
        -DevRoot $DevRoot `
        -SourceRef 'b3a969b8eda762d4792115b0185972782d8d8ed6' `
        -Experiment 'P0.2D5' `
        -FirmwareExperiment 'P0.2D4' `
        -OverlayPatch $hostOverlay
    if ($LASTEXITCODE -ne 0) {
        throw ('P0.2D5 host build failed with exit code ' + $LASTEXITCODE)
    }
}

& powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File $pairBuilder `
    -DevRoot $DevRoot `
    -Experiment 'P0.2D5' `
    -FirmwareExperiment 'P0.2D4' `
    -PackageExisting
if ($LASTEXITCODE -ne 0) {
    throw ('P0.2D5/D4 packaging failed with exit code ' + $LASTEXITCODE)
}
