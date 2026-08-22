#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$DevRoot = 'C:\AppleIIgsDev_02',
    [string]$FirmwareRoot,
    [string]$FirmwareSourceRef = 'HEAD',
    [string]$Experiment = 'P0.2C9',
    [string]$OverlayPatch
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptRoot
if ([string]::IsNullOrWhiteSpace($FirmwareRoot)) {
    $FirmwareRoot = Join-Path $repoRoot 'work\fujinet-firmware'
}
$firmwareRootFull = [IO.Path]::GetFullPath($FirmwareRoot)
if ($Experiment -notmatch '^P0\.2[CD][0-9]+$') {
    throw ('Invalid experiment identifier: ' + $Experiment)
}
$experimentSlug = $Experiment.ToLowerInvariant()
$diagVersion = $Experiment.Substring(4)
$releaseName = 'fastiwm-' + $experimentSlug + '-firmware'
$firmwareStem = 'fujinet-' + $experimentSlug + '-firmware'

$git = Get-Command git.exe -ErrorAction SilentlyContinue
if ($null -eq $git) { $git = Get-Command git -ErrorAction SilentlyContinue }
if ($null -eq $git) { throw 'Git is not available on PATH.' }
$python = Get-Command python.exe -ErrorAction SilentlyContinue
if ($null -eq $python) { $python = Get-Command python -ErrorAction SilentlyContinue }
if ($null -eq $python) { throw 'Python is not available on PATH.' }

if (-not (Test-Path -LiteralPath (Join-Path $firmwareRootFull '.git'))) {
    throw ('Pinned FujiNet Git checkout missing: ' + $firmwareRootFull)
}
$patchC9 = Join-Path $repoRoot 'tools\patch_fujinet_fastiwm_p02c9_ready.py'
if (-not (Test-Path -LiteralPath $patchC9 -PathType Leaf)) {
    throw ('P0.2C9 firmware transform missing: ' + $patchC9)
}
$currentOverlay = $null
if (-not [string]::IsNullOrWhiteSpace($OverlayPatch)) {
    $currentOverlay = [IO.Path]::GetFullPath($OverlayPatch)
    if (-not (Test-Path -LiteralPath $currentOverlay -PathType Leaf)) {
        throw ('Missing additional firmware overlay: ' + $currentOverlay)
    }
}

$firmwareSafeRoot = $firmwareRootFull.Replace('\', '/')
$gitPrefix = @(
    '-c', ('safe.directory=' + $firmwareSafeRoot),
    '-C', $firmwareRootFull
)
$sourceCommitLines = @(
    & $git.Source @gitPrefix rev-parse `
        --verify ($FirmwareSourceRef + '^{commit}') 2>&1
)
if ($LASTEXITCODE -ne 0) {
    $sourceCommitLines | ForEach-Object { Write-Host ([string]$_) }
    throw ('Unable to resolve clean FujiNet source ref: ' + $FirmwareSourceRef)
}
$sourceCommit = ([string]$sourceCommitLines[0]).Trim()

$requiredObjects = @(
    'lib/bus/iwm/iwm.cpp',
    'lib/bus/iwm/iwm_ll.cpp',
    'lib/bus/iwm/iwm_ll.h',
    'platformio-sample.ini'
)
$sourceBlobs = @()
foreach ($object in $requiredObjects) {
    $objectLines = @(
        & $git.Source @gitPrefix rev-parse `
            --verify ($sourceCommit + ':' + $object) 2>&1
    )
    if ($LASTEXITCODE -ne 0) {
        throw ('Missing FujiNet source object at ' + $sourceCommit + ': ' + $object)
    }
    $sourceBlobs += ($object + '=' + ([string]$objectLines[0]).Trim())
}

$tempBase = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
$tempRoot = [IO.Path]::GetFullPath((Join-Path $tempBase `
    ('fujinet-p02c9-' + [guid]::NewGuid().ToString('N'))))
$tempPrefix = $tempBase.TrimEnd('\') + '\'
if (-not $tempRoot.StartsWith(
    $tempPrefix,
    [StringComparison]::OrdinalIgnoreCase
)) {
    throw ('Refusing unsafe temporary path: ' + $tempRoot)
}

$snapshotZip = Join-Path $tempRoot 'firmware-source.zip'
$snapshotRoot = Join-Path $tempRoot 'fujinet-firmware'
$snapshotPioOut = Join-Path $snapshotRoot '.pio\build\fujiapple-rev0'
$snapshotRelease = Join-Path $tempRoot $releaseName
$publishRoot = Join-Path $repoRoot 'build'
$release = Join-Path $publishRoot $releaseName
$publishStaging = Join-Path $publishRoot `
    ('.fastiwm-' + $experimentSlug + '-firmware-publish-' +
        [guid]::NewGuid().ToString('N'))

New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null
try {
    Write-Host ''
    Write-Host ('=== FujiNet ' + $Experiment +
        ' isolated host-ready build ===') `
        -ForegroundColor Cyan
    Write-Host ('Firmware source: ' + $firmwareRootFull)
    Write-Host ('Source commit: ' + $sourceCommit)
    Write-Host 'The pinned FujiNet checkout will not be modified.'

    & $git.Source @gitPrefix archive `
        '--format=zip' ('--output=' + $snapshotZip) $sourceCommit
    if ($LASTEXITCODE -ne 0) { throw 'Unable to export clean FujiNet source.' }
    Expand-Archive -LiteralPath $snapshotZip -DestinationPath $snapshotRoot -Force

    & $python.Source $patchC9 `
        --project-root $repoRoot `
        --firmware-root $snapshotRoot
    if ($LASTEXITCODE -ne 0) {
        throw ('P0.2C9 firmware patch failed with exit code ' + $LASTEXITCODE)
    }
    if ($null -ne $currentOverlay) {
        & $python.Source $currentOverlay `
            --project-root $repoRoot `
            --firmware-root $snapshotRoot
        if ($LASTEXITCODE -ne 0) {
            throw ($Experiment + ' firmware overlay failed with exit code ' +
                $LASTEXITCODE)
        }
    }

    $sampleIni = Join-Path $snapshotRoot 'platformio-sample.ini'
    $platformIni = Join-Path $snapshotRoot 'platformio.ini'
    $ini = Get-Content -LiteralPath $sampleIni -Raw
    $replacements = @(
        @(';build_platform = BUILD_APPLE', 'build_platform = BUILD_APPLE'),
        @(';build_bus      = IWM', 'build_bus      = IWM'),
        @(
            ';build_board    = fujiapple-rev0         ; FujiApple Rev 0 Prototype',
            'build_board    = fujiapple-rev0         ; production Rev1 runtime detection'
        )
    )
    foreach ($pair in $replacements) {
        if ($ini.IndexOf($pair[0], [StringComparison]::Ordinal) -lt 0) {
            throw ('Missing platformio-sample pattern: ' + $pair[0])
        }
        $ini = $ini.Replace($pair[0], $pair[1])
    }
    $anchor = '    -D DEBUG_SPEED=${env.monitor_speed}'
    if ($ini.IndexOf($anchor, [StringComparison]::Ordinal) -lt 0) {
        throw 'Unable to locate common build_flags block.'
    }
    $ini = $ini.Replace(
        $anchor,
        $anchor + [Environment]::NewLine + '    -D IIGS_FAST_IWM_PROBE'
    )
    Set-Content -LiteralPath $platformIni -Value $ini -Encoding ASCII

    $forbidden = @(
        Select-String -LiteralPath $platformIni `
            -Pattern '^[ \t]*-D[ \t]+(REV1DETECT|MASTERIES_REV0|MASTERIES_REVAB|NO3STATE)([ \t]|$)' `
            -CaseSensitive
    )
    if ($forbidden.Count -gt 0) {
        $forbidden | ForEach-Object { Write-Host $_.Line -ForegroundColor Red }
        throw 'Forbidden FujiApple hardware override is active.'
    }
    Write-Host 'Production Rev1 runtime detection verified.' -ForegroundColor Green

    Push-Location $snapshotRoot
    try {
        & $python.Source -m platformio run -e fujiapple-rev0
        $pioExit = $LASTEXITCODE
    }
    finally {
        Pop-Location
    }
    if ($pioExit -ne 0) {
        throw ('PlatformIO build failed with exit code ' + $pioExit)
    }

    $firmwareBin = Join-Path $snapshotPioOut 'firmware.bin'
    $firmwareElf = Join-Path $snapshotPioOut 'firmware.elf'
    foreach ($required in @($firmwareBin, $firmwareElf)) {
        if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
            throw ('Missing FujiNet build output: ' + $required)
        }
    }

    $nm = Join-Path $env:USERPROFILE `
        '.platformio\packages\toolchain-xtensa-esp-elf\bin\xtensa-esp32-elf-nm.exe'
    if (-not (Test-Path -LiteralPath $nm -PathType Leaf)) {
        throw ('xtensa ELF inspection tool missing: ' + $nm)
    }
    $nmLines = @(& $nm -C $firmwareElf)
    if ($LASTEXITCODE -ne 0) { throw 'FujiNet ELF symbol inspection failed.' }
    $patchedBus = Get-Content `
        -LiteralPath (Join-Path $snapshotRoot 'lib\bus\iwm\iwm.cpp') -Raw
    $patchedLow = Get-Content `
        -LiteralPath (Join-Path $snapshotRoot 'lib\bus\iwm\iwm_ll.cpp') -Raw
    $isBurst = ($patchedBus + $patchedLow) -match `
        'fast_iwm_probe_burst_remaining'
    $isProviderStream = ($patchedBus + $patchedLow) -match `
        'FASTIWM D(?:[1-9][0-9]*) PROVIDER START'
    $isHostEndpoint = ($patchedBus + $patchedLow) -match `
        'FASTIWM D[0-9]+ ENDPOINT SET'
    $isPCMStream = ($patchedBus + $patchedLow) -match `
        'FASTIWM D[0-9]+ (PCM BURST ARMED|PROVIDER START)'
    $requiredSymbols = @(
        'iwm_send_fast_probe_spi',
        'fast_iwm_probe_armed',
        'fast_iwm_probe_request',
        'fast_iwm_probe_req_count',
        'fast_iwm_probe_reset_grace'
    )
    if ($isBurst) {
        $requiredSymbols += @(
            'fast_iwm_probe_burst_index',
            'fast_iwm_probe_burst_remaining',
            'fast_iwm_probe_waiting_for_ready_low',
            'fast_iwm_probe_burst_started'
        )
    }
    foreach ($symbol in $requiredSymbols) {
        if (@($nmLines | Where-Object { $_ -match $symbol }).Count -eq 0) {
            throw ('Required P0.2C9 symbol missing from firmware ELF: ' + $symbol)
        }
    }
    Write-Host ($Experiment + ' ELF symbol verification PASS.') `
        -ForegroundColor Green

    foreach ($marker in @(
        ('FASTIWM ' + $diagVersion + ' READY ARMED'),
        ('FASTIWM ' + $diagVersion + ' READY TRIGGER'),
        'FASTIWM TX START',
        'FASTIWM TX DONE'
    )) {
        if (($patchedBus + $patchedLow).IndexOf(
            $marker,
            [StringComparison]::Ordinal
        ) -lt 0) {
            throw ('Required firmware source marker missing: ' + $marker)
        }
    }
    if ($patchedBus -match 'AUTOSEND|AUTO TX') {
        throw 'Delayed autosend unexpectedly remains in P0.2C9 firmware.'
    }

    New-Item -ItemType Directory -Path $snapshotRelease -Force | Out-Null
    Copy-Item -LiteralPath $firmwareBin `
        -Destination (Join-Path $snapshotRelease `
            ($firmwareStem + '.bin')) -Force
    Copy-Item -LiteralPath $firmwareElf `
        -Destination (Join-Path $snapshotRelease `
            ($firmwareStem + '.elf')) -Force
    $firmwareMap = Join-Path $snapshotPioOut 'firmware.map'
    if (Test-Path -LiteralPath $firmwareMap -PathType Leaf) {
        Copy-Item -LiteralPath $firmwareMap `
            -Destination (Join-Path $snapshotRelease `
                ($firmwareStem + '.map')) -Force
    }
    Copy-Item -LiteralPath $platformIni `
        -Destination (Join-Path $snapshotRelease `
            'platformio.production-rev1.ini') -Force

    $transferDescription = if ($isProviderStream -and $isHostEndpoint) {
@"
WRITEBLOCK `$7FA556 accepts a D3EP DNS/IP and TCP port from FASTPROBE.
READBLOCK `$7FA559 starts that TCP client and `$7FA558 reports connection/FIFO
state. A ready `$7FA55A arm consumes one buffered 16 KiB provider batch as
32 x 512-byte PCM packets over the 2us link.
"@
    }
    elseif ($isProviderStream) {
@"
READBLOCK `$7FA559 starts a TCP client using Network netstream_host/port;
`$7FA558 reports connection/FIFO state. A ready `$7FA55A arm consumes one
buffered 16 KiB provider batch as 32 x 512-byte PCM packets over the 2us link.
"@
    }
    elseif ($isPCMStream) {
@"
READBLOCK `$7FA55A is decoded normally at 4us and arms 240 packets. Each
1010-to-1011 READY edge transmits 512 IWM-safe bytes encoding 448 arbitrary
PCM bytes. The payload is a deterministic unsigned 1..255 waveform.
"@
    }
    elseif ($isBurst) {
@"
READBLOCK `$7FA55A is decoded normally at 4us and arms 32 packets. Each
1010-to-1011 READY edge transmits one packet. The host drops READY to 1010
while validating, which re-arms the next packet without a transmit timer.
"@
    }
    else {
@"
READBLOCK `$7FA55A is decoded normally at 4us and arms one transfer. No fixed
transmit timer starts. The IIgs prepares IWM Read Data, drives
the proven phase state 1010, then raises PH0 to 1011 as an explicit READY
edge. Only that edge queues the private 2-MHz SPI waveform.
"@
    }
    $expectedSerial = if ($isProviderStream -and $isHostEndpoint) {
@"
  FASTIWM $diagVersion ENDPOINT SET host=... port=22510 source=IIgs
  FASTIWM $diagVersion PROVIDER START ...
  FASTIWM $diagVersion PROVIDER CONNECTED host=... port=22510
  FASTIWM $diagVersion PROVIDER BATCH ARMED packets=32 pcm=16384
  FASTIWM $diagVersion READY TRIGGER ... fifo=...
  FASTIWM $diagVersion PROVIDER BATCH DONE ... err=0
"@
    }
    elseif ($isProviderStream) {
@"
  FASTIWM $diagVersion PROVIDER START ...
  FASTIWM $diagVersion PROVIDER CONNECTED host=... port=22510
  FASTIWM $diagVersion PROVIDER BATCH ARMED packets=32 pcm=16384
  FASTIWM $diagVersion READY TRIGGER ... fifo=...
  FASTIWM $diagVersion PROVIDER BATCH DONE ... err=0
"@
    }
    elseif ($isPCMStream) {
@"
  FASTIWM D0 READY ARMED ... trigger=1011
  FASTIWM D0 PCM BURST ARMED packets=240 encoded=122880 pcm=107520
  FASTIWM D0 READY TRIGGER ... phase=0b
  FASTIWM TX START packet=0 ...
  FASTIWM TX DONE packet=239 ... err=0
  FASTIWM D0 PCM BURST DONE packets=240 encoded=122880 pcm=107520
"@
    }
    elseif ($isBurst) {
@"
  FASTIWM $diagVersion READY ARMED ... trigger=1011
  FASTIWM $diagVersion BURST ARMED packets=32 bytes=16384
  FASTIWM $diagVersion READY TRIGGER ... phase=0b
  FASTIWM TX START packet=0 ...
  FASTIWM TX DONE packet=31 ... err=0
  FASTIWM $diagVersion BURST DONE packets=32 bytes=16384
"@
    }
    else {
@"
  FASTIWM ARM block=7fa55a ...
  FASTIWM $diagVersion READY ARMED ... trigger=1011
  FASTIWM $diagVersion READY TRIGGER ... phase=0b
  FASTIWM TX START ...
  FASTIWM C5 BUS ACQUIRE DONE ret=0
  FASTIWM C5 BUS RELEASE ret=0
  FASTIWM TX DONE ... err=0
"@
    }

    @"
FujiNet $Experiment - paired host-ready 2us transmitter

Use only with matching FASTPROBE-$Experiment.po.

$transferDescription

Expected serial sequence:
$expectedSerial

Production Rev1 runtime detection is unchanged. Flash the application image
only at offset 0x10000.
"@ | Set-Content `
        -LiteralPath (Join-Path $snapshotRelease `
            ('README-' + $Experiment + '.txt')) `
        -Encoding ASCII

    $provenanceLines = @(
        ('FujiNet ' + $Experiment + ' build provenance'),
        ('FirmwareSourceCommit=' + $sourceCommit),
        ('ProjectPatchSHA256=' + (Get-FileHash -LiteralPath $patchC9 `
            -Algorithm SHA256).Hash.ToLowerInvariant()),
        'Environment=fujiapple-rev0 with production Rev1 runtime detection',
        'FastSPIClockHz=2000000',
        'Trigger=READBLOCK-7FA55A arm then phase 1010-to-1011 READY',
        ($sourceBlobs -join [Environment]::NewLine)
    )
    if ($null -ne $currentOverlay) {
        $provenanceLines += (
            'AdditionalOverlay=' + [IO.Path]::GetFileName($currentOverlay)
        )
        $provenanceLines += (
            'AdditionalOverlaySHA256=' +
            (Get-FileHash -LiteralPath $currentOverlay `
                -Algorithm SHA256).Hash.ToLowerInvariant()
        )
    }
    if ($isProviderStream) {
        $providerConfig = if ($isHostEndpoint) {
            'HostApp D3EP WRITEBLOCK-7FA556'
        }
        else {
            'Network.netstream_host/netstream_port'
        }
        $provenanceLines += @(
            'ProviderMode=TCP-raw-U8',
            ('ProviderConfig=' + $providerConfig),
            'ProviderDefaultHost=192.168.5.235',
            'ProviderDefaultPort=22510',
            'ProviderFIFOBytes=65536',
            'ProviderFIFOStorage=PSRAM-lazy',
            'BatchPackets=32',
            'BatchPCMBytes=16384',
            'EncodedBytesPerPacket=586',
            'PCMBytesPerPacket=512',
            'Codec=73 seven-byte groups plus one two-byte tail',
            'InterPacketHandshake=READY low 1010 then READY high 1011'
        )
    }
    elseif ($isPCMStream) {
        $provenanceLines += @(
            'BurstPackets=240',
            'EncodedBytesPerPacket=512',
            'PCMBytesPerPacket=448',
            'EncodedBytes=122880',
            'PCMBytes=107520',
            'Codec=seven low-7 PCM bytes plus one packed-MSB byte',
            'PCMSequence=unsigned bytes 1 through 255 repeating',
            'InterPacketHandshake=READY low 1010 then READY high 1011'
        )
    }
    elseif ($isBurst) {
        $provenanceLines += @(
            'BurstPackets=32',
            'PayloadBytesPerPacket=512',
            'BurstBytes=16384',
            'InterPacketHandshake=READY low 1010 then READY high 1011'
        )
    }
    $provenanceLines | Set-Content `
        -LiteralPath (Join-Path $snapshotRelease 'BUILD-PROVENANCE.txt') `
        -Encoding ASCII

    $hashLines = @()
    Get-ChildItem -LiteralPath $snapshotRelease -File |
        Where-Object { $_.Name -ne 'SHA256SUMS.txt' } |
        Sort-Object Name |
        ForEach-Object {
            $hash = Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256
            $hashLines += ($hash.Hash.ToLowerInvariant() + '  ' + $_.Name)
        }
    $hashLines | Set-Content `
        -LiteralPath (Join-Path $snapshotRelease 'SHA256SUMS.txt') `
        -Encoding ASCII

    New-Item -ItemType Directory -Path $publishRoot -Force | Out-Null
    Copy-Item -LiteralPath $snapshotRelease `
        -Destination $publishStaging -Recurse
    if (Test-Path -LiteralPath $release) {
        Remove-Item -LiteralPath $release -Recurse -Force
    }
    Move-Item -LiteralPath $publishStaging -Destination $release

    Write-Host ''
    Write-Host ('FUJINET ' + $Experiment + ' FIRMWARE BUILD COMPLETE') `
        -ForegroundColor Green
    Write-Host ('Firmware: ' + (Join-Path $release `
        ($firmwareStem + '.bin')))
    Write-Host ('Source commit: ' + $sourceCommit)
    Write-Host 'Pinned FujiNet checkout was untouched.' -ForegroundColor Green
}
finally {
    if (Test-Path -LiteralPath $publishStaging) {
        Remove-Item -LiteralPath $publishStaging -Recurse -Force
    }
    if (Test-Path -LiteralPath $tempRoot) {
        Remove-Item -LiteralPath $tempRoot -Recurse -Force
    }
}
