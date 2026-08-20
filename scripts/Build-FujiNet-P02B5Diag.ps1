#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$DevRoot = 'C:\AppleIIgsDev_02',
    [string]$ProjectRoot = 'C:\AppleIIgsDev_02\FujiNet-IIgs-Fast-IWM',
    [string]$PinnedFujiNetCommit = 'b0a9483463c93ab61279d265467159c0d27c9f82'
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

$thisScript = $MyInvocation.MyCommand.Path
if ([string]::IsNullOrWhiteSpace($thisScript)) {
    throw 'Unable to determine script path.'
}

$scriptRoot = Split-Path -Parent $thisScript
$repoRoot = Split-Path -Parent $scriptRoot
$firmwareRepo = Join-Path $ProjectRoot 'work\fujinet-firmware'
$worktree = Join-Path $DevRoot '_FastIWM_P02B5_Firmware'
$release = Join-Path $ProjectRoot 'build\fastiwm-p0.2b5-diag'

$pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
if ($null -eq $pythonCommand) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
}
if ($null -eq $pythonCommand) {
    throw 'Python is not available on PATH.'
}
$python = $pythonCommand.Source

if (-not (Test-Path -LiteralPath $firmwareRepo -PathType Container)) {
    throw ('FujiNet firmware repository missing: ' + $firmwareRepo)
}

& git.exe -C $firmwareRepo cat-file -e ($PinnedFujiNetCommit + '^{commit}')
if ($LASTEXITCODE -ne 0) {
    throw ('Pinned FujiNet commit missing: ' + $PinnedFujiNetCommit)
}

if (Test-Path -LiteralPath $worktree) {
    & git.exe -C $firmwareRepo worktree remove --force $worktree
    $removeExit = $LASTEXITCODE
    if ($removeExit -ne 0 -and (Test-Path -LiteralPath $worktree)) {
        Remove-Item -LiteralPath $worktree -Recurse -Force
    }
    & git.exe -C $firmwareRepo worktree prune
    if ($LASTEXITCODE -ne 0) {
        throw 'git worktree prune failed.'
    }
}

& git.exe -C $firmwareRepo worktree add --detach $worktree $PinnedFujiNetCommit
if ($LASTEXITCODE -ne 0) {
    throw 'Unable to create pinned FujiNet build worktree.'
}

try {
    $patch = Join-Path $repoRoot 'tools\patch_fujinet_fastiwm_p02b5diag.py'
    if (-not (Test-Path -LiteralPath $patch -PathType Leaf)) {
        throw ('P0.2B5 diagnostic patch missing: ' + $patch)
    }

    & $python $patch `
        --project-root $repoRoot `
        --firmware-root $worktree
    if ($LASTEXITCODE -ne 0) {
        throw 'P0.2B5 diagnostic patch failed.'
    }

    $sampleIni = Join-Path $worktree 'platformio-sample.ini'
    $platformIni = Join-Path $worktree 'platformio.ini'
    $ini = Get-Content -LiteralPath $sampleIni -Raw

    foreach ($pair in @(
        @(';build_platform = BUILD_APPLE','build_platform = BUILD_APPLE'),
        @(';build_bus      = IWM','build_bus      = IWM'),
        @(
            ';build_board    = fujiapple-rev0         ; FujiApple Rev 0 Prototype',
            'build_board    = fujiapple-rev0         ; production Rev1 runtime detection'
        )
    )) {
        if ($ini.IndexOf($pair[0],[System.StringComparison]::Ordinal) -lt 0) {
            throw ('Missing PlatformIO sample pattern: ' + $pair[0])
        }
        $ini = $ini.Replace($pair[0],$pair[1])
    }

    $flagAnchor = '    -D DEBUG_SPEED=${env.monitor_speed}'
    if ($ini.IndexOf($flagAnchor,[System.StringComparison]::Ordinal) -lt 0) {
        throw 'Unable to locate PlatformIO build_flags anchor.'
    }
    $ini = $ini.Replace(
        $flagAnchor,
        $flagAnchor + [Environment]::NewLine + '    -D IIGS_FAST_IWM_PROBE'
    )

    Set-Content -LiteralPath $platformIni -Value $ini -Encoding ASCII

    $forbidden = @(
        Select-String -LiteralPath $platformIni `
            -Pattern '^[ \t]*-D[ \t]+(REV1DETECT|MASTERIES_REV0|MASTERIES_REVAB|NO3STATE)([ \t]|$)' `
            -CaseSensitive
    )
    if ($forbidden.Count -gt 0) {
        throw 'Forbidden FujiApple hardware override is active.'
    }

    Write-Host ''
    Write-Host 'Building FujiNet P0.2B5 diagnostic firmware...' -ForegroundColor Cyan
    Write-Host 'Production Rev1 runtime detection; monitor baud 460800.'

    Push-Location $worktree
    try {
        & $python -m platformio run -e fujiapple-rev0
        $buildExit = $LASTEXITCODE
    }
    finally {
        Pop-Location
    }
    if ($buildExit -ne 0) {
        throw ('PlatformIO build failed with exit code ' + $buildExit)
    }

    $pioOut = Join-Path $worktree '.pio\build\fujiapple-rev0'
    $firmwareBin = Join-Path $pioOut 'firmware.bin'
    $firmwareElf = Join-Path $pioOut 'firmware.elf'

    foreach ($required in @($firmwareBin,$firmwareElf)) {
        if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
            throw ('Missing build artifact: ' + $required)
        }
    }

    $nm = Join-Path $env:USERPROFILE `
        '.platformio\packages\toolchain-xtensa-esp-elf\bin\xtensa-esp32-elf-nm.exe'
    if (-not (Test-Path -LiteralPath $nm -PathType Leaf)) {
        throw ('nm tool not found: ' + $nm)
    }

    $nmLines = @(& $nm -C $firmwareElf)
    if ($LASTEXITCODE -ne 0) {
        throw 'nm inspection failed.'
    }

    foreach ($symbol in @(
        'iwm_send_fast_probe_spi',
        'fast_iwm_probe_request',
        'fast_iwm_probe_arm_count',
        'fast_iwm_probe_request_count'
    )) {
        if (@($nmLines | Where-Object { $_ -match $symbol }).Count -eq 0) {
            throw ('Required diagnostic symbol not linked: ' + $symbol)
        }
    }

    if (Test-Path -LiteralPath $release) {
        Remove-Item -LiteralPath $release -Recurse -Force
    }
    New-Item -ItemType Directory -Path $release -Force | Out-Null

    Copy-Item -LiteralPath $firmwareBin `
        -Destination (Join-Path $release 'fujinet-p0.2b5-diag-firmware.bin') -Force
    Copy-Item -LiteralPath $firmwareElf `
        -Destination (Join-Path $release 'fujinet-p0.2b5-diag-firmware.elf') -Force
    Copy-Item -LiteralPath $platformIni `
        -Destination (Join-Path $release 'platformio.production-rev1.ini') -Force

    @'
Fast-IWM P0.2B5 diagnostic firmware

Use the existing FASTPROBE P0.2B4 host image.

This firmware adds serial diagnostics only in normal service context.
Expected messages when the host runs B4:

  FASTIWM DIAG events=01 phase=0e arm=1 req=0
  FASTIWM DIAG events=02 phase=0f arm=1 req=1
  FASTIWM TX START req=1
  FASTIWM TX DONE req=1

The exact event coalescing may combine 01 and 02 into events=03.

Monitor baud: 460800
Production Rev1 runtime detection.
REV1DETECT is OFF.

Flash application only at 0x10000.
'@ | Set-Content -LiteralPath (Join-Path $release 'README-P0.2B5.txt') -Encoding ASCII

    $hashLines = @()
    Get-ChildItem -LiteralPath $release -File |
        Sort-Object Name |
        ForEach-Object {
            $hash = Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256
            $hashLines += ($hash.Hash.ToLowerInvariant() + '  ' + $_.Name)
        }
    $hashLines | Set-Content -LiteralPath (Join-Path $release 'SHA256SUMS.txt') -Encoding ASCII

    Write-Host ''
    Write-Host '=== P0.2B5 DIAGNOSTIC FIRMWARE BUILD COMPLETE ===' -ForegroundColor Green
    Write-Host ('Firmware: ' + (Join-Path $release 'fujinet-p0.2b5-diag-firmware.bin'))
    Write-Host 'Host image: KEEP FASTPROBE-P0.2B4.po'
}
finally {
    if (Test-Path -LiteralPath $worktree) {
        & git.exe -C $firmwareRepo worktree remove --force $worktree
        $removeExit = $LASTEXITCODE
        if ($removeExit -ne 0 -and (Test-Path -LiteralPath $worktree)) {
            Write-Host 'Diagnostic worktree cleanup incomplete.' -ForegroundColor Yellow
        }
        & git.exe -C $firmwareRepo worktree prune
    }
}
