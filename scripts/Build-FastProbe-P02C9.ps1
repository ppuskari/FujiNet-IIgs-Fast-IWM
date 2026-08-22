#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$DevRoot = 'C:\AppleIIgsDev_02',
    [string]$SourceRef = 'HEAD',
    [string]$Experiment = 'P0.2C9',
    [string]$FirmwareExperiment,
    [string]$OverlayPatch
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptRoot
$expectedBaselineBlob = 'a6713b5f4df00889ade7757488042f1299b2495c'
if ($Experiment -notmatch '^P0\.2[CD][0-9]+$') {
    throw ('Invalid experiment identifier: ' + $Experiment)
}
if ([string]::IsNullOrWhiteSpace($FirmwareExperiment)) {
    $FirmwareExperiment = $Experiment
}
if ($FirmwareExperiment -notmatch '^P0\.2[CD][0-9]+$') {
    throw ('Invalid firmware experiment identifier: ' + $FirmwareExperiment)
}
$experimentSlug = $Experiment.ToLowerInvariant()
$releaseName = 'fastiwm-' + $experimentSlug + '-host'
$hostStem = 'FASTPROBE-' + $Experiment

$git = Get-Command git.exe -ErrorAction SilentlyContinue
if ($null -eq $git) { $git = Get-Command git -ErrorAction SilentlyContinue }
if ($null -eq $git) { throw 'Git is not available on PATH.' }
$python = Get-Command python.exe -ErrorAction SilentlyContinue
if ($null -eq $python) { $python = Get-Command python -ErrorAction SilentlyContinue }
if ($null -eq $python) { throw 'Python is not available on PATH.' }

$devRootFull = [IO.Path]::GetFullPath($DevRoot)
$cp2 = Join-Path $devRootFull 'tools\cp2\cp2.exe'
if (-not (Test-Path -LiteralPath $cp2 -PathType Leaf)) {
    throw ('CiderPress II cp2.exe missing: ' + $cp2)
}

$currentPatchC8 = Join-Path $repoRoot 'tools\patch_spbench_fastiwm_p02c8.py'
$currentPatchC9 = Join-Path $repoRoot 'tools\patch_spbench_fastiwm_p02c9.py'
foreach ($required in @($currentPatchC8, $currentPatchC9)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw ('Missing host transform: ' + $required)
    }
}
$currentOverlay = $null
if (-not [string]::IsNullOrWhiteSpace($OverlayPatch)) {
    $currentOverlay = [IO.Path]::GetFullPath($OverlayPatch)
    if (-not (Test-Path -LiteralPath $currentOverlay -PathType Leaf)) {
        throw ('Missing additional host overlay: ' + $currentOverlay)
    }
}

$gitSafeRoot = $repoRoot.Replace('\', '/')
$gitPrefix = @('-c', ('safe.directory=' + $gitSafeRoot), '-C', $repoRoot)
$sourceCommitLines = @(
    & $git.Source @gitPrefix rev-parse --verify ($SourceRef + '^{commit}') 2>&1
)
if ($LASTEXITCODE -ne 0) {
    $sourceCommitLines | ForEach-Object { Write-Host ([string]$_) }
    throw ('Unable to resolve clean host source ref: ' + $SourceRef)
}
$sourceCommit = ([string]$sourceCommitLines[0]).Trim()

$baselineObject = $sourceCommit + ':iigs/spbench/src/SPBench.s'
$baselineBlobLines = @(
    & $git.Source @gitPrefix rev-parse --verify $baselineObject 2>&1
)
if ($LASTEXITCODE -ne 0) {
    $baselineBlobLines | ForEach-Object { Write-Host ([string]$_) }
    throw 'Unable to resolve the tracked SPBENCH baseline.'
}
$baselineBlob = ([string]$baselineBlobLines[0]).Trim()
if ($baselineBlob -ne $expectedBaselineBlob) {
    throw (
        'Source ref ' + $SourceRef + ' does not contain the proven P0.1B ' +
        'baseline. Expected blob ' + $expectedBaselineBlob +
        ', found ' + $baselineBlob + '.'
    )
}

$tempBase = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
$tempRoot = [IO.Path]::GetFullPath((Join-Path $tempBase `
    ('fastprobe-p02c9-' + [guid]::NewGuid().ToString('N'))))
$tempPrefix = $tempBase.TrimEnd('\') + '\'
if (-not $tempRoot.StartsWith(
    $tempPrefix,
    [StringComparison]::OrdinalIgnoreCase
)) {
    throw ('Refusing unsafe temporary path: ' + $tempRoot)
}

$snapshotZip = Join-Path $tempRoot 'source.zip'
$snapshotRoot = Join-Path $tempRoot 'source'
$snapshotPatchC8 = Join-Path $snapshotRoot `
    'tools\patch_spbench_fastiwm_p02c8.py'
$snapshotPatchC9 = Join-Path $snapshotRoot `
    'tools\patch_spbench_fastiwm_p02c9.py'
$currentOverlayDependencies = @(
    'tools\patch_spbench_fastiwm_p02c10.py',
    'tools\patch_spbench_fastiwm_p02c11.py',
    'tools\patch_spbench_fastiwm_p02c12.py',
    'tools\patch_spbench_fastiwm_p02c13.py',
    'tools\patch_spbench_fastiwm_p02c14.py',
    'tools\patch_spbench_fastiwm_p02c15.py',
    'tools\patch_spbench_fastiwm_p02c16.py',
    'tools\patch_spbench_fastiwm_p02c17.py',
    'tools\patch_spbench_fastiwm_p02c18.py',
    'tools\patch_spbench_fastiwm_p02c19.py',
    'tools\patch_spbench_fastiwm_p02d0.py',
    'tools\patch_spbench_fastiwm_p02d1_provider.py',
    'tools\patch_spbench_fastiwm_p02d2_softreturn.py',
    'tools\patch_spbench_fastiwm_p02d3_endpoint.py',
    'tools\patch_spbench_fastiwm_p02d4_spi_wait.py',
    'tools\patch_spbench_fastiwm_p02d5_thunk_flags.py'
) | ForEach-Object { Join-Path $repoRoot $_ } |
    Where-Object { Test-Path -LiteralPath $_ -PathType Leaf }
$snapshotOverlay = $null
if ($null -ne $currentOverlay) {
    $snapshotOverlay = Join-Path $snapshotRoot `
        ('tools\' + [IO.Path]::GetFileName($currentOverlay))
}
$snapshotRelease = Join-Path $snapshotRoot ('build\' + $releaseName)
$publishRoot = Join-Path $repoRoot 'build'
$release = Join-Path $publishRoot $releaseName
$publishStaging = Join-Path $publishRoot `
    ('.fastiwm-' + $experimentSlug + '-host-publish-' +
        [guid]::NewGuid().ToString('N'))

$isPCMBuild = $Experiment -match '^P0\.2D[0-9]+$'
$tool225Macros = $null
$tool225Binary = $null
$tool225MacrosHash = 'e06cb32675d806174516355736c825114f24b79846e0cc7d96dbbceef731e043'
$tool225BinaryHash = 'ca8ba2c41ef49e047596bc9c3314b12caa2c374830dd1e0e24ca84eac565d7de'
if ($isPCMBuild) {
    $streamerRoot = Join-Path $devRootFull 'Petars-Ensoniq-Streamer'
    $tool225Macros = Join-Path $streamerRoot `
        'client-source\M3R36A\22m512\EthernetStreamer\Tool225.Macs.s'
    $tool225Binary = Join-Path $streamerRoot 'Binaries\TOOL225#BA0000'
    foreach ($required in @($tool225Macros, $tool225Binary)) {
        if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
            throw ('Missing frozen Tool225 support file: ' + $required)
        }
    }
    $actualMacrosHash = (Get-FileHash -LiteralPath $tool225Macros `
        -Algorithm SHA256).Hash.ToLowerInvariant()
    $actualBinaryHash = (Get-FileHash -LiteralPath $tool225Binary `
        -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualMacrosHash -ne $tool225MacrosHash) {
        throw ('Tool225 macro hash mismatch: ' + $actualMacrosHash)
    }
    if ($actualBinaryHash -ne $tool225BinaryHash) {
        throw ('Tool225 golden binary hash mismatch: ' + $actualBinaryHash)
    }
}

New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null
try {
    Write-Host ''
    Write-Host ('=== FASTPROBE ' + $Experiment +
        ' isolated clean-source build ===') `
        -ForegroundColor Cyan
    Write-Host ('Source commit: ' + $sourceCommit)
    Write-Host ('Proven SPBENCH blob: ' + $baselineBlob)
    Write-Host 'Local IWMProbe/SPBench edits will not be read or modified.'

    & $git.Source @gitPrefix archive `
        '--format=zip' ('--output=' + $snapshotZip) $sourceCommit
    if ($LASTEXITCODE -ne 0) { throw 'Unable to export clean host source.' }
    Expand-Archive -LiteralPath $snapshotZip -DestinationPath $snapshotRoot -Force

    # C8 and C9 are current experimental overlays. All older transforms and
    # the assembly baseline come from the verified clean Git snapshot.
    Copy-Item -LiteralPath $currentPatchC8 -Destination $snapshotPatchC8 -Force
    Copy-Item -LiteralPath $currentPatchC9 -Destination $snapshotPatchC9 -Force
    foreach ($dependency in $currentOverlayDependencies) {
        Copy-Item -LiteralPath $dependency `
            -Destination (Join-Path $snapshotRoot `
                ('tools\' + [IO.Path]::GetFileName($dependency))) -Force
    }
    if ($null -ne $currentOverlay) {
        Copy-Item -LiteralPath $currentOverlay `
            -Destination $snapshotOverlay -Force
    }
    if ($isPCMBuild) {
        Copy-Item -LiteralPath $tool225Macros `
            -Destination (Join-Path $snapshotRoot `
                'iigs\spbench\src\Tool225.Macs.s') -Force
    }

    $patchB3 = Join-Path $snapshotRoot 'tools\patch_spbench_p01b3_v2.py'
    $fixB3 = Join-Path $snapshotRoot 'tools\fix_spbench_p01b3_branches.py'
    $fixC = Join-Path $snapshotRoot 'tools\fix_fastiwm_p02c_branches.py'
    $baseBuilder = Join-Path $snapshotRoot 'scripts\Build-SPBench-P01B.ps1'
    foreach ($required in @(
        $patchB3,
        $fixB3,
        $snapshotPatchC9,
        $fixC,
        $baseBuilder
    )) {
        if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
            throw ('Missing clean host build input: ' + $required)
        }
    }

    Push-Location $snapshotRoot
    try {
        & $python.Source $patchB3
        if ($LASTEXITCODE -ne 0) { throw 'SPBENCH P0.1B3 patch failed.' }
        & $python.Source $fixB3
        if ($LASTEXITCODE -ne 0) { throw 'SPBENCH branch fix failed.' }
        & $python.Source $snapshotPatchC9 --project-root $snapshotRoot
        if ($LASTEXITCODE -ne 0) { throw 'FASTPROBE P0.2C9 patch failed.' }
        if ($null -ne $snapshotOverlay) {
            & $python.Source $snapshotOverlay --project-root $snapshotRoot
            if ($LASTEXITCODE -ne 0) {
                throw ('FASTPROBE ' + $Experiment + ' overlay failed.')
            }
        }
        & $python.Source $fixC --project-root $snapshotRoot
        if ($LASTEXITCODE -ne 0) { throw 'FASTPROBE branch fix failed.' }
    }
    finally {
        Pop-Location
    }

    & powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File $baseBuilder -DevRoot $devRootFull
    if ($LASTEXITCODE -ne 0) {
        throw ('Underlying Merlin32 build failed with exit code ' + $LASTEXITCODE)
    }

    $sourceRoot = Join-Path $snapshotRoot 'iigs\spbench\src'
    $sourceFile = Join-Path $sourceRoot 'SPBench.s'
    $listing = Join-Path $sourceRoot 'SPBENCH_S01_SPBENCH_Output.txt'
    $sourceBin = Join-Path $snapshotRoot `
        'build\spbench-p0.1b\release\SPBENCH#B30000'
    foreach ($required in @($sourceFile, $listing, $sourceBin)) {
        if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
            throw ('Missing assembled host output: ' + $required)
        }
    }

    $sourceLines = Get-Content -LiteralPath $sourceFile
    $listingLines = Get-Content -LiteralPath $listing
    # Verify every mask instruction that is present in the selected overlay.
    # C12 deliberately removes the older C-bit-only acceptance test, so that
    # instruction must not be a mandatory feature of every later experiment.
    $encodingChecks = @(
        @{ Needle = 'and   #IWMModeMask'; Bytes = '29 1F'; Required = $true },
        @{ Needle = 'and   #IWMCell2usMask'; Bytes = '29 08'; Required = $false },
        @{ Needle = 'cmp   #FastReadySampleLimit'; Bytes = 'C9 08'; Required = $false }
    )
    $verifiedRows = @()
    foreach ($check in $encodingChecks) {
        $needle = [string]$check.Needle
        $bytes = [string]$check.Bytes
        $matches = @(
            Select-String -LiteralPath $sourceFile -SimpleMatch $needle
        )
        if ($matches.Count -lt 1) {
            if ([bool]$check.Required) {
                throw ('Unable to locate assembly encoding check: ' + $needle)
            }
            continue
        }
        foreach ($match in $matches) {
            $pattern = 'SPBench\.s\s+' + $match.LineNumber + '\s+\|'
            $rows = @($listingLines | Where-Object { $_ -match $pattern })
            if ($rows.Count -ne 1) {
                throw ('Unable to identify listing row for: ' + $needle)
            }
            $row = [string]$rows[0]
            $bytePattern = ':\s+' + [regex]::Escape($bytes) + '\s+\|'
            if ($row -notmatch $bytePattern) {
                throw ('Unsafe immediate encoding; expected ' + $bytes + ': ' + $row)
            }
            $verifiedRows += $row.Trim()
        }
    }
    Write-Host 'Verified all present 8-bit IWM mask encodings.' `
        -ForegroundColor Green

    New-Item -ItemType Directory -Path $snapshotRelease -Force | Out-Null
    $fastBin = Join-Path $snapshotRelease ($hostStem + '#B30000')
    $image = Join-Path $snapshotRelease ($hostStem + '.po')
    $readme = Join-Path $snapshotRelease `
        ('README-' + $Experiment + '#040000')
    $provenance = Join-Path $snapshotRelease 'BUILD-PROVENANCE.txt'
    Copy-Item -LiteralPath $sourceBin -Destination $fastBin -Force

    $exactModeRequired = [bool]($sourceLines -match 'P0\.2C12:')
    $isBurst = [bool]($sourceLines -match 'FastBurstPackets')
    $isProviderStream = [bool]($sourceLines -match 'FASTPROBE P0\.2D(?:[1-9][0-9]*)')
    $isHostEndpoint = [bool]($sourceLines -match 'D3ProviderConfigBlockLo')
    $isPCMStream = [bool]($sourceLines -match 'FASTPROBE P0\.2D[0-9]+')
    $modePolicy = if ($exactModeRequired) {
@"
Exact mode `$0F is required. Its C bit selects 2us cells; H/L provide the
documented asynchronous timing and full-byte Read Data latch behavior.
"@
    }
    else {
@"
Exact mode `$0F is preferred; a live mode with C=1 is sufficient because C
selects 2us cells and the interrupt-free polling loop is inside the short
data-latch interval.
"@
    }

    $transferDescription = if ($isProviderStream -and $isHostEndpoint) {
@"
WRITEBLOCK `$7FA556 sends the provider DNS/IP and TCP port selected in the
IIgs application. READBLOCK `$7FA559 then starts FujiNet's TCP provider and
`$7FA558 polls buffered status. Each ready `$7FA55A arm transfers 32 packets;
586 IWM-safe bytes decode to 512 chronological PCM bytes per packet.
Frozen Tool225 starts after 480 KiB and consumes a locked 512 KiB mono ring.
"@
    }
    elseif ($isProviderStream) {
@"
READBLOCK `$7FA559 starts FujiNet's configured TCP provider and `$7FA558
polls its buffered status. Each ready `$7FA55A arm transfers 32 packets;
586 IWM-safe bytes decode to exactly 512 chronological PCM bytes per packet.
Frozen Tool225 starts after 480 KiB and consumes a locked 512 KiB mono ring.
"@
    }
    elseif ($isPCMStream) {
@"
The ordinary SmartPort READBLOCK `$7FA55A arms 240 packets. Each physical
packet contains 512 IWM-safe bytes and decodes to 448 arbitrary PCM bytes.
After a 43008-byte prefill, frozen Tool225 consumes the same 128 KiB source
ring at 21972.65 bytes/sec while the foreground 2us producer continues.
"@
    }
    elseif ($isBurst) {
@"
The ordinary SmartPort READBLOCK `$7FA55A arms one 32-packet burst at the
proven 4us rate. Each 1010-to-1011 READY edge requests one deterministic
512-byte packet; READY returns low while the host validates that packet.
"@
    }
    else {
@"
The ordinary SmartPort READBLOCK `$7FA55A arms one private transfer at
the proven 4us rate. The IIgs then inspects and prepares the IWM receive mode.
"@
    }
    $expectedSuccess = if ($isProviderStream) {
@"
  STREAM STOPPED: provider PCM played without underrun.
  min lead blocks remains positive; underrun=`$0000.
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

    @"
$hostStem - paired host-ready IWM 2us link

Use only with FujiNet $FirmwareExperiment host-ready firmware.

$transferDescription
$modePolicy

Only after the IIgs receiver is live does it establish phase 1010 and raise
PH0 to 1011. That READY edge causes FujiNet to send the deterministic packet.
This removes the old 50ms timer race and C8's unbounded mode-write loop.

Expected success:
$expectedSuccess
"@ | Set-Content -LiteralPath $readme -Encoding ASCII

    $provenanceLines = @(
        ('FASTPROBE ' + $Experiment + ' build provenance'),
        ('PairedFirmware=' + $FirmwareExperiment),
        ('ProjectSourceCommit=' + $sourceCommit),
        ('BaselineSPBenchBlob=' + $baselineBlob),
        ('PatchC8SHA256=' + (Get-FileHash -LiteralPath $currentPatchC8 `
            -Algorithm SHA256).Hash.ToLowerInvariant()),
        ('PatchC9SHA256=' + (Get-FileHash -LiteralPath $currentPatchC9 `
            -Algorithm SHA256).Hash.ToLowerInvariant()),
        'Protocol=READBLOCK-7FA55A then host-ready phase 1010-to-1011',
        'RequestedIWMMode=0F'
    )
    if ($exactModeRequired) {
        $provenanceLines += 'AcceptedIWMMode=0F'
    }
    else {
        $provenanceLines += 'Accepted2usMask=08'
    }
    $provenanceLines += @(
        'ModeWritePasses=3',
        ($verifiedRows -join [Environment]::NewLine)
    )
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
            'BatchPackets=32',
            'BatchPCMBytes=16384',
            'EncodedBytesPerPacket=586',
            'PCMBytesPerPacket=512',
            'Codec=73 seven-byte groups plus one two-byte tail',
            'DOCSampleRate=21972.65',
            'DOCStartPrefillBytes=491520',
            'DOCRingBytes=524288',
            'Tool225MacrosSHA256=' + $tool225MacrosHash,
            'Tool225BinarySHA256=' + $tool225BinaryHash,
            'BatchTiming=provider-ready poll then no-wait fast receive/decode/commit'
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
            'DOCSampleRate=21972.65',
            'DOCStartPrefillBytes=43008',
            'DOCRingBytes=131072',
            'Tool225MacrosSHA256=' + $tool225MacrosHash,
            'Tool225BinarySHA256=' + $tool225BinaryHash,
            'BurstTiming=route plus receive plus decode plus ring commit'
        )
    }
    elseif ($isBurst) {
        $provenanceLines += @(
            'BurstPackets=32',
            'PayloadBytesPerPacket=512',
            'BurstBytes=16384',
            'BurstTiming=route plus receive plus validation plus restore'
        )
    }
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
    $provenanceLines | Set-Content -LiteralPath $provenance -Encoding ASCII

    & $cp2 create-disk-image $image 32mb ProDOS
    if ($LASTEXITCODE -ne 0) { throw 'cp2 create-disk-image failed.' }
    & $cp2 rename $image : FASTPROBE
    if ($LASTEXITCODE -ne 0) { throw 'cp2 rename failed.' }
    & $cp2 add --from-naps --strip-paths $image $fastBin
    if ($LASTEXITCODE -ne 0) { throw 'cp2 add FASTPROBE failed.' }
    & $cp2 add --from-naps --strip-paths $image $readme
    if ($LASTEXITCODE -ne 0) { throw 'cp2 add README failed.' }
    if ($isPCMStream) {
        $releaseTool = Join-Path $snapshotRelease 'TOOL225#BA0000'
        Copy-Item -LiteralPath $tool225Binary -Destination $releaseTool -Force
        & $cp2 mkdir $image SYSTEM
        if ($LASTEXITCODE -ne 0) { throw 'cp2 mkdir SYSTEM failed.' }
        $systemArchive = $image + ':SYSTEM'
        & $cp2 mkdir $systemArchive TOOLS
        if ($LASTEXITCODE -ne 0) { throw 'cp2 mkdir SYSTEM/TOOLS failed.' }
        $toolArchive = $image + ':SYSTEM:TOOLS'
        & $cp2 add --from-naps --strip-paths $toolArchive $releaseTool
        if ($LASTEXITCODE -ne 0) { throw 'cp2 add Tool225 failed.' }
    }
    & $cp2 test $image
    if ($LASTEXITCODE -ne 0) { throw 'cp2 filesystem test failed.' }

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
    Write-Host ('FASTPROBE ' + $Experiment + ' HOST BUILD COMPLETE') `
        -ForegroundColor Green
    Write-Host ('PO: ' + (Join-Path $release ($hostStem + '.po')))
    Write-Host ('Source commit: ' + $sourceCommit)
    Write-Host 'Caller working-tree assembly sources were untouched.' `
        -ForegroundColor Green
}
finally {
    if (Test-Path -LiteralPath $publishStaging) {
        Remove-Item -LiteralPath $publishStaging -Recurse -Force
    }
    if (Test-Path -LiteralPath $tempRoot) {
        Remove-Item -LiteralPath $tempRoot -Recurse -Force
    }
}
