#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$DevRoot = 'C:\AppleIIgsDev_02',
    [string]$FirmwareRoot = '',
    [switch]$ForceDirty
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0

$thisScript = $MyInvocation.MyCommand.Path
if ([string]::IsNullOrWhiteSpace($thisScript)) {
    throw 'Unable to determine preparation script path.'
}

$scriptRoot = Split-Path -Parent $thisScript
$repoRoot = Split-Path -Parent $scriptRoot

if ([string]::IsNullOrWhiteSpace($FirmwareRoot)) {
    $FirmwareRoot = Join-Path $repoRoot 'work\fujinet-firmware'
}

$patchScript = Join-Path $repoRoot 'tools\patch_fujinet_fastiwm_p02b.py'
$expectedCommit = 'b0a9483463c93ab61279d265467159c0d27c9f82'
$expectedBranch = 'petar/iigs-fast-iwm-p0'

if (-not (Test-Path -LiteralPath $FirmwareRoot -PathType Container)) {
    throw ('FujiNet firmware checkout not found: ' + $FirmwareRoot)
}
if (-not (Test-Path -LiteralPath $patchScript -PathType Leaf)) {
    throw ('Patch script not found: ' + $patchScript)
}

$pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
if ($null -eq $pythonCommand) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
}
if ($null -eq $pythonCommand) {
    throw 'Python is not available on PATH.'
}

Push-Location $FirmwareRoot
try {
    $inside = & git.exe rev-parse --is-inside-work-tree
    $gitExit = $LASTEXITCODE
    if ($gitExit -ne 0 -or $inside -ne 'true') {
        throw 'FirmwareRoot is not a Git working tree.'
    }

    $branch = (& git.exe branch --show-current).Trim()
    if ($LASTEXITCODE -ne 0) {
        throw 'Unable to determine FujiNet firmware branch.'
    }

    $head = (& git.exe rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0) {
        throw 'Unable to determine FujiNet firmware HEAD.'
    }

    $baseObject = & git.exe cat-file -t $expectedCommit 2>$null
    if ($LASTEXITCODE -ne 0 -or $baseObject -ne 'commit') {
        throw ('Pinned FujiNet commit is not present locally: ' + $expectedCommit)
    }

    & git.exe merge-base --is-ancestor $expectedCommit HEAD
    $ancestorExit = $LASTEXITCODE
    if ($ancestorExit -ne 0) {
        throw ('Current FujiNet HEAD is not descended from pinned baseline ' + $expectedCommit)
    }

    $dirtyBefore = @(& git.exe status --porcelain)
    if ($LASTEXITCODE -ne 0) {
        throw 'git status failed in FujiNet checkout.'
    }

    $alreadyPatched = $false
    $llCpp = Join-Path $FirmwareRoot 'lib\bus\iwm\iwm_ll.cpp'
    if (Test-Path -LiteralPath $llCpp -PathType Leaf) {
        $alreadyPatched = Select-String `
            -LiteralPath $llCpp `
            -SimpleMatch 'fast_iwm_probe_armed' `
            -Quiet
    }

    if ($dirtyBefore.Count -gt 0 -and -not $alreadyPatched -and -not $ForceDirty) {
        Write-Host ''
        Write-Host 'FujiNet checkout has local modifications:' -ForegroundColor Yellow
        $dirtyBefore | ForEach-Object { Write-Host $_ }
        throw 'Refusing to patch a dirty FujiNet tree. Commit/stash it, or pass -ForceDirty intentionally.'
    }

    Write-Host ''
    Write-Host 'FujiNet Fast-IWM P0.2B preparation' -ForegroundColor Cyan
    Write-Host ('Firmware root : ' + $FirmwareRoot)
    Write-Host ('Branch        : ' + $branch)
    Write-Host ('HEAD          : ' + $head)
    Write-Host ('Pinned base   : ' + $expectedCommit)

    if ($branch -ne $expectedBranch) {
        Write-Host ('NOTE: expected experiment branch is ' + $expectedBranch) -ForegroundColor Yellow
        Write-Host 'Continuing because the pinned baseline is an ancestor of current HEAD.' -ForegroundColor Yellow
    }
}
finally {
    Pop-Location
}

Push-Location $repoRoot
try {
    & $pythonCommand.Source $patchScript --firmware-root $FirmwareRoot
    $patchExit = $LASTEXITCODE
}
finally {
    Pop-Location
}
if ($patchExit -ne 0) {
    throw ('FujiNet P0.2B patch failed with exit code ' + $patchExit)
}

Push-Location $FirmwareRoot
try {
    Write-Host ''
    Write-Host 'Patched FujiNet files:' -ForegroundColor Green
    & git.exe status --short
    if ($LASTEXITCODE -ne 0) {
        throw 'git status failed after patch.'
    }

    $markers = @(
        'IIGS_FAST_IWM_PROBE',
        'iwm_send_fast_probe_spi',
        'fast_iwm_probe_armed',
        'fastcfg.clock_speed_hz = 2 * MHZ'
    )

    $combined = (
        Get-Content -LiteralPath 'lib\bus\iwm\iwm_ll.h' -Raw
    ) + (
        Get-Content -LiteralPath 'lib\bus\iwm\iwm_ll.cpp' -Raw
    )

    foreach ($marker in $markers) {
        if ($combined.IndexOf($marker, [System.StringComparison]::Ordinal) -lt 0) {
            throw ('Missing expected firmware marker after patch: ' + $marker)
        }
    }
}
finally {
    Pop-Location
}

Write-Host ''
Write-Host 'FUJINET P0.2B SOURCE PREPARATION COMPLETE' -ForegroundColor Green
Write-Host ''
Write-Host 'The patch does NOT globally accelerate SmartPort.'
Write-Host 'Normal SmartPort TX remains 1 MHz / 4 us.'
Write-Host 'The private probe adds a second 2 MHz TX handle under:'
Write-Host '  -D IIGS_FAST_IWM_PROBE'
Write-Host ''
Write-Host 'Do not flash a firmware build until the actual FujiApple board/build target is confirmed.' -ForegroundColor Yellow
