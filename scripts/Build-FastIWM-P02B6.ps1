#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$DevRoot = 'C:\AppleIIgsDev_02',
    [string]$FirmwareRepo = '',
    [string]$PinnedFujiNetCommit = 'b0a9483463c93ab61279d265467159c0d27c9f82'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0

$thisScript = $MyInvocation.MyCommand.Path
if ([string]::IsNullOrWhiteSpace($thisScript)) {
    throw 'Unable to determine build script path.'
}

$scriptRoot = Split-Path -Parent $thisScript
$repoRoot = Split-Path -Parent $scriptRoot

if ([string]::IsNullOrWhiteSpace($FirmwareRepo)) {
    $FirmwareRepo = Join-Path $repoRoot 'work\fujinet-firmware'
}

$pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
if ($null -eq $pythonCommand) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
}
if ($null -eq $pythonCommand) {
    throw 'Python is not available on PATH.'
}
$Python = $pythonCommand.Source

if (-not (Test-Path -LiteralPath $FirmwareRepo -PathType Container)) {
    throw ('FujiNet firmware repository not found: ' + $FirmwareRepo)
}

$workRoot = Join-Path $DevRoot '_FastIWM_P02B6_Firmware'
$firmwareWork = Join-Path $workRoot 'fujinet'
$releaseRoot = Join-Path $repoRoot 'build\fastiwm-p0.2b6-paired'

if (Test-Path -LiteralPath $firmwareWork) {
    & git.exe -C $FirmwareRepo worktree remove --force $firmwareWork
    $removeExit = $LASTEXITCODE
    if ($removeExit -ne 0 -and (Test-Path -LiteralPath $firmwareWork)) {
        Remove-Item -LiteralPath $firmwareWork -Recurse -Force
    }
    & git.exe -C $FirmwareRepo worktree prune
    if ($LASTEXITCODE -ne 0) {
        throw 'Unable to prune stale FujiNet worktree.'
    }
}

New-Item -ItemType Directory -Path $workRoot -Force | Out-Null

& git.exe -C $FirmwareRepo cat-file -e ($PinnedFujiNetCommit + '^{commit}')
if ($LASTEXITCODE -ne 0) {
    throw ('Pinned FujiNet commit is unavailable: ' + $PinnedFujiNetCommit)
}

& git.exe -C $FirmwareRepo worktree add --detach $firmwareWork $PinnedFujiNetCommit
if ($LASTEXITCODE -ne 0) {
    throw 'Unable to create pinned FujiNet worktree.'
}

try {
    if (Test-Path -LiteralPath $releaseRoot) {
        Remove-Item -LiteralPath $releaseRoot -Recurse -Force
    }
    New-Item -ItemType Directory -Path $releaseRoot -Force | Out-Null

    Write-Host ''
    Write-Host '=== Build FASTPROBE P0.2B6 host ===' -ForegroundColor Cyan

    $hostPatch = Join-Path $repoRoot 'tools\patch_fastprobe_p02b6_statusarm.py'
    & $Python $hostPatch --project-root $repoRoot
    if ($LASTEXITCODE -ne 0) {
        throw 'FASTPROBE P0.2B6 source patch failed.'
    }

    $baseHostBuilder = Join-Path $repoRoot 'scripts\Build-FastProbe-P02B.ps1'
    & powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File $baseHostBuilder -DevRoot $DevRoot
    if ($LASTEXITCODE -ne 0) {
        throw 'FASTPROBE P0.2B6 assembly/package build failed.'
    }

    $baseHostRelease = Join-Path $repoRoot 'build\fastprobe-p0.2b\release'
    Copy-Item -LiteralPath (Join-Path $baseHostRelease 'FASTPROBE-P0.2B.po') `
        -Destination (Join-Path $releaseRoot 'FASTPROBE-P0.2B6.po') -Force
    Copy-Item -LiteralPath (Join-Path $baseHostRelease 'FASTPROBE#B30000') `
        -Destination (Join-Path $releaseRoot 'FASTPROBE-P0.2B6#B30000') -Force

    Write-Host ''
    Write-Host '=== Build FujiNet P0.2B6 STATUS-arm firmware ===' -ForegroundColor Cyan

    $firmwarePatch = Join-Path $repoRoot 'tools\patch_fujinet_fastiwm_p02b6_statusarm.py'
    & $Python $firmwarePatch `
        --project-root $repoRoot `
        --firmware-root $firmwareWork
    if ($LASTEXITCODE -ne 0) {
        throw 'FujiNet P0.2B6 source patch failed.'
    }

    $sampleIni = Join-Path $firmwareWork 'platformio-sample.ini'
    $platformIni = Join-Path $firmwareWork 'platformio.ini'
    $ini = Get-Content -LiteralPath $sampleIni -Raw

    foreach ($pair in @(
        @(';build_platform = BUILD_APPLE','build_platform = BUILD_APPLE'),
        @(';build_bus      = IWM','build_bus      = IWM'),
        @(';build_board    = fujiapple-rev0         ; FujiApple Rev 0 Prototype',
          'build_board    = fujiapple-rev0         ; production Rev1 runtime detection')
    )) {
        if ($ini.IndexOf($pair[0], [System.StringComparison]::Ordinal) -lt 0) {
            throw ('Missing PlatformIO sample pattern: ' + $pair[0])
        }
        $ini = $ini.Replace($pair[0], $pair[1])
    }

    $flagAnchor = '    -D DEBUG_SPEED=${env.monitor_speed}'
    if ($ini.IndexOf($flagAnchor, [System.StringComparison]::Ordinal) -lt 0) {
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
        $forbidden | ForEach-Object { Write-Host $_.Line -ForegroundColor Red }
        throw 'Forbidden FujiApple hardware override is active.'
    }

    & $Python -m platformio run -e fujiapple-rev0
    $pioExit = $LASTEXITCODE
    if ($pioExit -ne 0) {
        throw ('PlatformIO firmware build failed with exit code ' + $pioExit)
    }

    $pioOut = Join-Path $firmwareWork '.pio\build\fujiapple-rev0'
    $firmwareBin = Join-Path $pioOut 'firmware.bin'
    $firmwareElf = Join-Path $pioOut 'firmware.elf'
    if (-not (Test-Path -LiteralPath $firmwareBin -PathType Leaf)) {
        throw 'firmware.bin was not produced.'
    }
    if (-not (Test-Path -LiteralPath $firmwareElf -PathType Leaf)) {
        throw 'firmware.elf was not produced.'
    }

    $nm = Join-Path $env:USERPROFILE `
        '.platformio\packages\toolchain-xtensa-esp-elf\bin\xtensa-esp32-elf-nm.exe'
    if (-not (Test-Path -LiteralPath $nm -PathType Leaf)) {
        throw ('xtensa nm tool missing: ' + $nm)
    }

    $nmLines = @(& $nm -C $firmwareElf)
    if ($LASTEXITCODE -ne 0) {
        throw 'Unable to inspect firmware ELF.'
    }

    foreach ($symbol in @(
        'iwm_send_fast_probe_spi',
        'fast_iwm_probe_autosend_pending',
        'fast_iwm_probe_autosend_due_ms'
    )) {
        if (@($nmLines | Where-Object { $_ -match $symbol }).Count -eq 0) {
            throw ('Required P0.2B6 symbol is not linked: ' + $symbol)
        }
    }

    Write-Host 'P0.2B6 ELF verification PASS.' -ForegroundColor Green

    Copy-Item -LiteralPath $firmwareBin `
        -Destination (Join-Path $releaseRoot 'fujinet-p0.2b6-firmware.bin') -Force
    Copy-Item -LiteralPath $firmwareElf `
        -Destination (Join-Path $releaseRoot 'fujinet-p0.2b6-firmware.elf') -Force
    Copy-Item -LiteralPath $platformIni `
        -Destination (Join-Path $releaseRoot 'platformio.production-rev1.ini') -Force

    @'
Fast-IWM P0.2B6 - legal SmartPort STATUS arm + delayed 2-us autosend

Host negotiation:
  Standard SmartPort STATUS command $00
  unit $01
  device-specific status code $AA

FujiNet behavior:
  Returns normal HELLO WORLD status response at ordinary 4-us timing.
  Arms one private packet and schedules it 20 ms later.
  Delayed packet uses the dedicated 2-MHz Fast-IWM transmitter.

The host enters direct IWM read mode immediately after the ROM status call
returns. No private 1110/1111 phase signature is used.

Production Rev1 uses normal runtime detection.
REV1DETECT / MASTERIES_* / NO3STATE remain disabled.
'@ | Set-Content -LiteralPath (Join-Path $releaseRoot 'README-P0.2B6.txt') -Encoding ASCII

    $hashLines = @()
    Get-ChildItem -LiteralPath $releaseRoot -File |
        Sort-Object Name |
        ForEach-Object {
            $hash = Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256
            $hashLines += ($hash.Hash.ToLowerInvariant() + '  ' + $_.Name)
        }
    $hashLines | Set-Content `
        -LiteralPath (Join-Path $releaseRoot 'SHA256SUMS.txt') -Encoding ASCII

    $zipPath = $releaseRoot + '.zip'
    if (Test-Path -LiteralPath $zipPath) {
        Remove-Item -LiteralPath $zipPath -Force
    }
    Compress-Archive -Path (Join-Path $releaseRoot '*') `
        -DestinationPath $zipPath -CompressionLevel Optimal
    $zipHash = Get-FileHash -LiteralPath $zipPath -Algorithm SHA256

    Write-Host ''
    Write-Host '=== P0.2B6 PAIRED BUILD COMPLETE ===' -ForegroundColor Green
    Write-Host ('Release:  ' + $releaseRoot)
    Write-Host ('Firmware: ' + (Join-Path $releaseRoot 'fujinet-p0.2b6-firmware.bin'))
    Write-Host ('PO:       ' + (Join-Path $releaseRoot 'FASTPROBE-P0.2B6.po'))
    Write-Host ('ZIP:      ' + $zipPath)
    Write-Host ('SHA256:   ' + $zipHash.Hash.ToLowerInvariant())
}
finally {
    if (Test-Path -LiteralPath $firmwareWork) {
        & git.exe -C $FirmwareRepo worktree remove --force $firmwareWork
        if ($LASTEXITCODE -ne 0 -and (Test-Path -LiteralPath $firmwareWork)) {
            Write-Host 'FujiNet build worktree cleanup incomplete.' -ForegroundColor Yellow
        }
        & git.exe -C $FirmwareRepo worktree prune
    }
}
