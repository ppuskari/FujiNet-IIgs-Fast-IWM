#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$DevRoot = 'C:\AppleIIgsDev_02',
    [string]$FirmwareRoot,
    [string]$SourceRef = 'HEAD',
    [string]$FirmwareSourceRef = 'HEAD',
    [ValidatePattern('^P0\.2[CD][0-9]+$')]
    [string]$Experiment = 'P0.2C9',
    [ValidatePattern('^$|^P0\.2[CD][0-9]+$')]
    [string]$FirmwareExperiment = '',
    [string]$HostOverlayPatch = '.\tools\patch_spbench_fastiwm_p02c9.py',
    [string]$FirmwareOverlayPatch = '.\tools\patch_fujinet_fastiwm_p02c9_ready.py',
    [switch]$PackageExisting
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptRoot
if ([string]::IsNullOrWhiteSpace($FirmwareRoot)) {
    $FirmwareRoot = Join-Path $repoRoot 'work\fujinet-firmware'
}
if ([string]::IsNullOrWhiteSpace($FirmwareExperiment)) {
    $FirmwareExperiment = $Experiment
}

$hostBuilder = Join-Path $scriptRoot 'Build-FastProbe-P02C9.ps1'
$firmwareBuilder = Join-Path $scriptRoot 'Build-FujiNet-P02C9.ps1'
foreach ($required in @($hostBuilder, $firmwareBuilder)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw ('Missing paired build input: ' + $required)
    }
}

Write-Host ''
Write-Host ("=== $Experiment paired host/FujiNet build ===") -ForegroundColor Cyan
Write-Host 'Protocol: 4us SmartPort arm, host-ready edge, 2us payload.'

if (-not $PackageExisting) {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File $hostBuilder `
        -DevRoot $DevRoot `
        -SourceRef $SourceRef `
        -Experiment $Experiment `
        -FirmwareExperiment $FirmwareExperiment `
        -OverlayPatch $HostOverlayPatch
    if ($LASTEXITCODE -ne 0) {
        throw ("$Experiment host build failed with exit code " + $LASTEXITCODE)
    }

    & powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File $firmwareBuilder `
        -DevRoot $DevRoot `
        -FirmwareRoot $FirmwareRoot `
        -FirmwareSourceRef $FirmwareSourceRef `
        -Experiment $FirmwareExperiment `
        -OverlayPatch $FirmwareOverlayPatch
    if ($LASTEXITCODE -ne 0) {
        throw ("$Experiment firmware build failed with exit code " + $LASTEXITCODE)
    }
}
else {
    Write-Host 'Packaging the already-validated host and firmware releases.'
}

$experimentLower = $Experiment.ToLowerInvariant()
$firmwareExperimentLower = $FirmwareExperiment.ToLowerInvariant()
$hostRelease = Join-Path $repoRoot ("build\fastiwm-$experimentLower-host")
$firmwareRelease = Join-Path $repoRoot `
    ("build\fastiwm-$firmwareExperimentLower-firmware")
$pairRelease = Join-Path $repoRoot ("build\fastiwm-$experimentLower-pair")
$pairStaging = Join-Path (Join-Path $repoRoot 'build') `
    (".fastiwm-$experimentLower-pair-" + [guid]::NewGuid().ToString('N'))
foreach ($required in @($hostRelease, $firmwareRelease)) {
    if (-not (Test-Path -LiteralPath $required -PathType Container)) {
        throw ('Paired release input missing: ' + $required)
    }
}

try {
    New-Item -ItemType Directory -Path $pairStaging -Force | Out-Null
    $hostOut = Join-Path $pairStaging 'host'
    $firmwareOut = Join-Path $pairStaging 'firmware'
    Copy-Item -LiteralPath $hostRelease -Destination $hostOut -Recurse
    Copy-Item -LiteralPath $firmwareRelease `
        -Destination $firmwareOut -Recurse

    $hostProvenance = Join-Path $hostOut 'BUILD-PROVENANCE.txt'
    $hostProvenanceText = if (Test-Path -LiteralPath $hostProvenance -PathType Leaf) {
        Get-Content -LiteralPath $hostProvenance -Raw
    }
    else { '' }
    $isProviderStream = $hostProvenanceText -match 'ProviderMode=TCP-raw-U8'
    $isHostEndpoint = $hostProvenanceText -match `
        'ProviderConfig=HostApp D3EP WRITEBLOCK-7FA556'
    $isPCMStream = $hostProvenanceText -match 'BurstPackets=240'
    $isBurst = $hostProvenanceText -match 'BurstPackets=32'
    $protocolDescription = if ($isProviderStream -and $isHostEndpoint) {
@"
$Experiment prompts for the provider DNS/IP and TCP port, defaulting to
192.168.5.235:22510, and sends that endpoint to $FirmwareExperiment with a
private SmartPort WRITEBLOCK before START. FujiNet buffers 16 KiB before each
32-packet fast batch. Every 586-byte IWM-safe packet becomes exactly 512 PCM
bytes in the IIgs 512 KiB Tool225 source ring.
"@
    }
    elseif ($isProviderStream) {
@"
$FirmwareExperiment connects to the configured raw-U8 TCP provider and
buffers 16 KiB before each 32-packet fast batch. Every 586-byte IWM-safe
packet becomes exactly 512 PCM bytes in the IIgs 512 KiB Tool225 source ring.
"@
    }
    elseif ($isPCMStream) {
@"
$FirmwareExperiment sends 240 packets from one arm. The IIgs decodes each
512-byte IWM-safe packet into 448 arbitrary PCM bytes, starts frozen Tool225
after a 43008-byte prefill, and continues filling the DOC source ring live.
"@
    }
    elseif ($isBurst) {
@"
$FirmwareExperiment sends 32 packets from one arm. Each packet uses one
1010-to-1011 READY edge; the IIgs validates 512 bytes before requesting the
next packet and reports validated bytes/sec and kbit/sec.
"@
    }
    else {
@"
$FirmwareExperiment deliberately waits for the host's 1010-to-1011 READY edge before
transmitting the 2us packet.
"@
    }
    $expectedResult = if ($isProviderStream) {
@"
  STREAM STOPPED: provider PCM played without underrun.
  underrun=`$0000 and a positive minimum producer lead.
"@
    }
    elseif ($isPCMStream) {
@"
  FAST PCM PASS: 240 packets / 107520 bytes verified.
  DOC PLAY PASS: 21973 Hz drain complete, no underrun.
"@
    }
    elseif ($isBurst) {
        '  FAST BURST PASS: 32 exact packets / 16 KiB verified.'
    }
    else {
        '  FAST PASS: exact 512-byte 2us payload verified.'
    }
    $providerSetup = if ($isProviderStream -and $isHostEndpoint) {
@"

Before running FASTPROBE, start the existing 22-mono provider. At the IIgs
prompts, press Return twice for 192.168.5.235:22510 or type an override.
No FujiNet web/SD NetStream setting is required.
"@
    }
    elseif ($isProviderStream) {
@"

Before running FASTPROBE, start the existing 22-mono provider and set
FujiNet Network Stream host to that machine and port to 22510.
"@
    }
    else { '' }

    @"
$Experiment host / $FirmwareExperiment firmware 2us IWM experiment

Deploy both halves as a matched pair:

1. Flash firmware\fujinet-$firmwareExperimentLower-firmware.bin as the FujiNet application
   image at offset 0x10000.
2. Copy/mount host\FASTPROBE-$Experiment.po and run FASTPROBE.

Do not mix the $Experiment host with P0.2C4/P0.2C5 delayed-autosend firmware.
$protocolDescription
$providerSetup

Expected IIgs result:
$expectedResult
"@ | Set-Content -LiteralPath (Join-Path $pairStaging "README-$Experiment.txt") `
        -Encoding ASCII

    $hashLines = @()
    Get-ChildItem -LiteralPath $pairStaging -File -Recurse |
        Where-Object { $_.Name -ne 'SHA256SUMS.txt' } |
        Sort-Object FullName |
        ForEach-Object {
            $relative = $_.FullName.Substring($pairStaging.Length + 1)
            $relative = $relative.Replace('\', '/')
            $hash = Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256
            $hashLines += ($hash.Hash.ToLowerInvariant() + '  ' + $relative)
        }
    $hashLines | Set-Content `
        -LiteralPath (Join-Path $pairStaging 'SHA256SUMS.txt') `
        -Encoding ASCII

    if (Test-Path -LiteralPath $pairRelease) {
        Remove-Item -LiteralPath $pairRelease -Recurse -Force
    }
    Move-Item -LiteralPath $pairStaging -Destination $pairRelease
}
finally {
    if (Test-Path -LiteralPath $pairStaging) {
        Remove-Item -LiteralPath $pairStaging -Recurse -Force
    }
}

Write-Host ''
Write-Host ("$Experiment MATCHED PAIR BUILD COMPLETE") -ForegroundColor Green
Write-Host ('Release: ' + $pairRelease)
Write-Host ('Host: ' + (Join-Path $pairRelease ("host\FASTPROBE-$Experiment.po")))
Write-Host ('Firmware: ' + (Join-Path $pairRelease `
    ("firmware\fujinet-$firmwareExperimentLower-firmware.bin")))
