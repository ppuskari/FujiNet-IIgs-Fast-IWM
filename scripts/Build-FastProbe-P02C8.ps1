#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$DevRoot = 'C:\AppleIIgsDev_02',
    [string]$SourceRef = 'HEAD',
    [switch]$IsolatedBuild
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptRoot
$expectedBaselineBlob = 'a6713b5f4df00889ade7757488042f1299b2495c'

# Exact-match experiment transforms must never run against the caller's
# working tree. Export a verified Git snapshot, build there, then publish only
# a completed release directory. This preserves local assembly experiments.
if (-not $IsolatedBuild) {
    $git = Get-Command git.exe -ErrorAction SilentlyContinue
    if ($null -eq $git) { $git = Get-Command git -ErrorAction SilentlyContinue }
    if ($null -eq $git) { throw 'Git is not available on PATH.' }

    $currentPatchC8 = Join-Path $repoRoot `
        'tools\patch_spbench_fastiwm_p02c8.py'
    if (-not (Test-Path -LiteralPath $currentPatchC8 -PathType Leaf)) {
        throw ('Missing P0.2C8 transform: ' + $currentPatchC8)
    }

    $gitSafeRoot = $repoRoot.Replace('\', '/')
    $gitPrefix = @(
        '-c', ('safe.directory=' + $gitSafeRoot),
        '-C', $repoRoot
    )
    $sourceCommitLines = @(
        & $git.Source @gitPrefix rev-parse `
            --verify ($SourceRef + '^{commit}') 2>&1
    )
    if ($LASTEXITCODE -ne 0) {
        $sourceCommitLines | ForEach-Object { Write-Host ([string]$_) }
        throw ('Unable to resolve clean source ref: ' + $SourceRef)
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
    $tempRoot = Join-Path $tempBase `
        ('fastprobe-p02c8-' + [guid]::NewGuid().ToString('N'))
    $tempRoot = [IO.Path]::GetFullPath($tempRoot)
    $tempPrefix = $tempBase.TrimEnd('\') + '\'
    if (-not $tempRoot.StartsWith(
        $tempPrefix,
        [StringComparison]::OrdinalIgnoreCase
    )) {
        throw ('Refusing unsafe temporary path: ' + $tempRoot)
    }

    $snapshotZip = Join-Path $tempRoot 'source.zip'
    $snapshotRoot = Join-Path $tempRoot 'source'
    $snapshotScript = Join-Path $snapshotRoot `
        'scripts\Build-FastProbe-P02C8.ps1'
    $snapshotPatchC8 = Join-Path $snapshotRoot `
        'tools\patch_spbench_fastiwm_p02c8.py'
    $snapshotRelease = Join-Path $snapshotRoot `
        'build\fastiwm-p0.2c8-host'
    $publishRoot = Join-Path $repoRoot 'build'
    $release = Join-Path $publishRoot 'fastiwm-p0.2c8-host'
    $publishStaging = Join-Path $publishRoot `
        ('.fastiwm-p0.2c8-publish-' + [guid]::NewGuid().ToString('N'))

    New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null
    try {
        Write-Host ''
        Write-Host '=== FASTPROBE P0.2C8 isolated clean-source build ===' `
            -ForegroundColor Cyan
        Write-Host ('Source commit: ' + $sourceCommit)
        Write-Host ('Proven SPBENCH blob: ' + $baselineBlob)
        Write-Host 'Local assembly edits will not be read or modified.'

        & $git.Source @gitPrefix archive `
            '--format=zip' ('--output=' + $snapshotZip) $sourceCommit
        if ($LASTEXITCODE -ne 0) {
            throw 'Unable to export clean source snapshot.'
        }
        Expand-Archive -LiteralPath $snapshotZip `
            -DestinationPath $snapshotRoot -Force

        # Allow the currently running, not-yet-committed C8 workflow to prove
        # itself while all baseline source and prior transforms remain clean.
        Copy-Item -LiteralPath $MyInvocation.MyCommand.Path `
            -Destination $snapshotScript -Force
        Copy-Item -LiteralPath $currentPatchC8 `
            -Destination $snapshotPatchC8 -Force

        & powershell.exe -NoProfile -ExecutionPolicy Bypass `
            -File $snapshotScript `
            -DevRoot $DevRoot `
            -SourceRef $sourceCommit `
            -IsolatedBuild
        if ($LASTEXITCODE -ne 0) {
            throw ('Isolated P0.2C8 build failed with exit code ' + $LASTEXITCODE)
        }
        if (-not (Test-Path -LiteralPath $snapshotRelease -PathType Container)) {
            throw ('Isolated release directory not found: ' + $snapshotRelease)
        }

        New-Item -ItemType Directory -Path $publishRoot -Force | Out-Null
        Copy-Item -LiteralPath $snapshotRelease `
            -Destination $publishStaging -Recurse
        if (Test-Path -LiteralPath $release) {
            Remove-Item -LiteralPath $release -Recurse -Force
        }
        Move-Item -LiteralPath $publishStaging -Destination $release

        Write-Host ''
        Write-Host 'ISOLATED P0.2C8 RELEASE PUBLISHED' -ForegroundColor Green
        Write-Host ('Release: ' + $release)
        Write-Host ('Source commit: ' + $sourceCommit)
        Write-Host 'Caller working-tree sources were not modified.' -ForegroundColor Green
    }
    finally {
        if (Test-Path -LiteralPath $publishStaging) {
            Remove-Item -LiteralPath $publishStaging -Recurse -Force
        }
        if (Test-Path -LiteralPath $tempRoot) {
            Remove-Item -LiteralPath $tempRoot -Recurse -Force
        }
    }

    exit 0
}

if (Test-Path -LiteralPath (Join-Path $repoRoot '.git')) {
    throw 'IsolatedBuild may run only inside the exported clean snapshot.'
}

$python = Get-Command python.exe -ErrorAction SilentlyContinue
if ($null -eq $python) { $python = Get-Command python -ErrorAction SilentlyContinue }
if ($null -eq $python) { throw 'Python is not available on PATH.' }

$patchB3 = Join-Path $repoRoot 'tools\patch_spbench_p01b3_v2.py'
$fixB3 = Join-Path $repoRoot 'tools\fix_spbench_p01b3_branches.py'
$patchC8 = Join-Path $repoRoot 'tools\patch_spbench_fastiwm_p02c8.py'
$fixC = Join-Path $repoRoot 'tools\fix_fastiwm_p02c_branches.py'
$baseBuilder = Join-Path $scriptRoot 'Build-SPBench-P01B.ps1'
$devRootFull = [IO.Path]::GetFullPath($DevRoot)
$cp2 = Join-Path $devRootFull 'tools\cp2\cp2.exe'

foreach ($required in @($patchB3, $fixB3, $patchC8, $fixC, $baseBuilder, $cp2)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw ('Missing required build input: ' + $required)
    }
}

Write-Host ''
Write-Host '=== FASTPROBE P0.2C8 host-only build ===' -ForegroundColor Cyan
Write-Host 'KEEP FujiNet P0.2C4 delayed-autosend firmware.'
Write-Host 'One fix: force M=8 before the IWM mode-mask immediate.'
Write-Host ''

Push-Location $repoRoot
try {
    & $python.Source $patchB3
    if ($LASTEXITCODE -ne 0) { throw 'SPBENCH P0.1B3 patch failed.' }

    & $python.Source $fixB3
    if ($LASTEXITCODE -ne 0) { throw 'SPBENCH P0.1B3 branch fix failed.' }

    & $python.Source $patchC8 --project-root $repoRoot
    if ($LASTEXITCODE -ne 0) { throw 'FASTPROBE P0.2C8 host patch failed.' }

    & $python.Source $fixC --project-root $repoRoot
    if ($LASTEXITCODE -ne 0) { throw 'FASTPROBE P0.2C branch fix failed.' }
}
finally {
    Pop-Location
}

& powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File $baseBuilder -DevRoot $devRootFull
if ($LASTEXITCODE -ne 0) {
    throw ('Underlying Merlin32 build failed with exit code ' + $LASTEXITCODE)
}

$sourceRoot = Join-Path $repoRoot 'iigs\spbench\src'
$sourceFile = Join-Path $sourceRoot 'SPBench.s'
$listing = Join-Path $sourceRoot 'SPBENCH_S01_SPBENCH_Output.txt'
$sourceRelease = Join-Path $repoRoot 'build\spbench-p0.1b\release'
$sourceBin = Join-Path $sourceRelease 'SPBENCH#B30000'
foreach ($required in @($sourceFile, $listing, $sourceBin)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw ('Missing assembled output: ' + $required)
    }
}

$modeMaskMatch = @(
    Select-String -LiteralPath $sourceFile -SimpleMatch 'and   #IWMModeMask'
) | Select-Object -Last 1
if ($null -eq $modeMaskMatch) {
    throw 'Unable to locate SetIWMModeC mode-mask source line.'
}
$sourceLinePattern = 'SPBench\.s\s+' + $modeMaskMatch.LineNumber + '\s+\|'
$listingRows = @(
    Get-Content -LiteralPath $listing | Where-Object { $_ -match $sourceLinePattern }
)
if ($listingRows.Count -ne 1) {
    throw 'Unable to identify the assembled SetIWMModeC mode-mask row.'
}
$modeMaskListing = [string]$listingRows[0]
if ($modeMaskListing -notmatch ':\s+29 1F\s+\|') {
    throw ('Unsafe mode-mask encoding; expected exactly 29 1F: ' + $modeMaskListing)
}
Write-Host 'Verified SetIWMModeC encoding: 29 1F (8-bit immediate).' `
    -ForegroundColor Green

$release = Join-Path $repoRoot 'build\fastiwm-p0.2c8-host'
if (Test-Path -LiteralPath $release) {
    Remove-Item -LiteralPath $release -Recurse -Force
}
New-Item -ItemType Directory -Path $release -Force | Out-Null

$fastBin = Join-Path $release 'FASTPROBE-P0.2C8#B30000'
$image = Join-Path $release 'FASTPROBE-P0.2C8.po'
$readme = Join-Path $release 'README-P0.2C8#040000'
$provenance = Join-Path $release 'BUILD-PROVENANCE.txt'

Copy-Item -LiteralPath $sourceBin -Destination $fastBin -Force

@'
FASTPROBE P0.2C8 - 8-bit-safe IIgs IWM 2us receive mode

KEEP the already-flashed FujiNet P0.2C4 delayed-autosend firmware.
No FujiNet rebuild or reflash is required.

P0.2C7 reached the IWM mode-programming routine but BRKed at $0A/0640.
The CPU was in 8-bit accumulator mode while Merlin had emitted the
mode-mask immediate as 29 1F 00. The CPU consumed 29 1F and executed the
remaining 00 byte as BRK before entering the receive loop.

P0.2C8 makes one host-side correction:
  - SetIWMModeC explicitly executes SEP #$20;
  - the assembler emits AND #$1F as exactly 29 1F;
  - all P0.2C7 IWM mode, receive, reset, and restore behavior is retained.

Expected success message:
  FAST PASS: exact 512-byte 2us payload verified.
'@ | Set-Content -LiteralPath $readme -Encoding ASCII

@(
    'FASTPROBE P0.2C8 build provenance',
    ('SourceCommit=' + $SourceRef),
    ('BaselineSPBenchBlob=' + $expectedBaselineBlob),
    'SetIWMModeMaskEncoding=29 1F',
    ('ListingRow=' + $modeMaskListing.Trim())
) | Set-Content -LiteralPath $provenance -Encoding ASCII

& $cp2 create-disk-image $image 32mb ProDOS
if ($LASTEXITCODE -ne 0) { throw 'cp2 create-disk-image failed.' }
& $cp2 rename $image : FASTPROBE
if ($LASTEXITCODE -ne 0) { throw 'cp2 rename failed.' }
& $cp2 add --from-naps --strip-paths $image $fastBin
if ($LASTEXITCODE -ne 0) { throw 'cp2 add FASTPROBE failed.' }
& $cp2 add --from-naps --strip-paths $image $readme
if ($LASTEXITCODE -ne 0) { throw 'cp2 add README failed.' }
& $cp2 test $image
if ($LASTEXITCODE -ne 0) { throw 'cp2 filesystem test failed.' }

$hashLines = @()
foreach ($name in @(
    'FASTPROBE-P0.2C8#B30000',
    'FASTPROBE-P0.2C8.po',
    'README-P0.2C8#040000',
    'BUILD-PROVENANCE.txt'
)) {
    $path = Join-Path $release $name
    $hash = Get-FileHash -LiteralPath $path -Algorithm SHA256
    $hashLines += ($hash.Hash.ToLowerInvariant() + '  ' + $name)
}
$hashLines | Set-Content `
    -LiteralPath (Join-Path $release 'SHA256SUMS.txt') -Encoding ASCII

Write-Host ''
Write-Host 'FASTPROBE P0.2C8 HOST BUILD COMPLETE' -ForegroundColor Green
Write-Host ('PO: ' + $image)
Write-Host 'FujiNet: KEEP P0.2C4 firmware.' -ForegroundColor Green
