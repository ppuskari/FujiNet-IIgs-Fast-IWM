#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$DevRoot = 'C:\AppleIIgsDev_02',
    [Parameter(Mandatory=$true)]
    [string]$FirmwareRoot
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0

$thisScript = $MyInvocation.MyCommand.Path
if ([string]::IsNullOrWhiteSpace($thisScript)) {
    throw 'Unable to determine build script path.'
}

$scriptRoot = Split-Path -Parent $thisScript
$repoRoot = Split-Path -Parent $scriptRoot

$python = Get-Command python.exe -ErrorAction SilentlyContinue
if ($null -eq $python) {
    $python = Get-Command python -ErrorAction SilentlyContinue
}
if ($null -eq $python) {
    throw 'Python is not available on PATH.'
}

$patchB3 = Join-Path $repoRoot 'tools\patch_spbench_p01b3_v2.py'
$fixB3 = Join-Path $repoRoot 'tools\fix_spbench_p01b3_branches.py'
$patchC3Host = Join-Path $repoRoot 'tools\patch_spbench_fastiwm_p02c3.py'
$patchC3Firmware = Join-Path $repoRoot 'tools\patch_fujinet_fastiwm_p02c3.py'
$baseHostBuilder = Join-Path $scriptRoot 'Build-SPBench-P01B.ps1'
$cp2 = Join-Path $DevRoot 'tools\cp2\cp2.exe'

foreach ($required in @(
    $patchB3,
    $fixB3,
    $patchC3Host,
    $patchC3Firmware,
    $baseHostBuilder,
    $cp2
)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw ('Missing required build input: ' + $required)
    }
}

if (-not (Test-Path -LiteralPath $FirmwareRoot -PathType Container)) {
    throw ('FujiNet firmware root missing: ' + $FirmwareRoot)
}

Write-Host ''
Write-Host '=== Fast-IWM P0.2C3 paired autosend build ===' -ForegroundColor Cyan
Write-Host ('Project root : ' + $repoRoot)
Write-Host ('Firmware root: ' + $FirmwareRoot)
Write-Host ''

# ------------------------------------------------------------------
# Host build: proven B3 direct SmartPort base -> P0.2C -> C3 overlay.
# ------------------------------------------------------------------
Push-Location $repoRoot
try {
    & $python.Source $patchB3
    if ($LASTEXITCODE -ne 0) {
        throw 'SPBENCH P0.1B3 patch failed.'
    }

    & $python.Source $fixB3
    if ($LASTEXITCODE -ne 0) {
        throw 'SPBENCH P0.1B3 branch fix failed.'
    }

    & $python.Source $patchC3Host --project-root $repoRoot
    if ($LASTEXITCODE -ne 0) {
        throw 'FASTPROBE P0.2C3 host overlay failed.'
    }
}
finally {
    Pop-Location
}

& powershell.exe `
    -NoProfile `
    -ExecutionPolicy Bypass `
    -File $baseHostBuilder `
    -DevRoot $DevRoot

if ($LASTEXITCODE -ne 0) {
    throw ('Underlying Merlin32 host build failed with exit code ' + $LASTEXITCODE)
}

$hostSourceRelease = Join-Path $repoRoot 'build\spbench-p0.1b\release'
$hostSourceBin = Join-Path $hostSourceRelease 'SPBENCH#B30000'
if (-not (Test-Path -LiteralPath $hostSourceBin -PathType Leaf)) {
    throw ('Assembled host S16 not found: ' + $hostSourceBin)
}

$releaseRoot = Join-Path $repoRoot 'build\fastiwm-p0.2c3-paired'
$hostRelease = Join-Path $releaseRoot 'host'
$firmwareRelease = Join-Path $releaseRoot 'fujinet'

if (Test-Path -LiteralPath $releaseRoot) {
    Remove-Item -LiteralPath $releaseRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $hostRelease -Force | Out-Null
New-Item -ItemType Directory -Path $firmwareRelease -Force | Out-Null

$hostBin = Join-Path $hostRelease 'FASTPROBE#B30000'
$hostPo = Join-Path $hostRelease 'FASTPROBE-P0.2C3.po'
$hostReadme = Join-Path $hostRelease 'README#040000'

Copy-Item -LiteralPath $hostSourceBin -Destination $hostBin -Force

@'
FASTPROBE P0.2C3 - SmartPort-arm autonomous Fast-IWM send

Requires matching FujiNet P0.2C3 firmware.

Sequence:
  standard SmartPort READBLOCK $7FA55A arms FujiNet at 4 us,
  normal 512-byte arm response completes,
  FujiNet starts a 20 ms timer AFTER that response returns,
  IIgs returns from ROM and waits in direct IWM Read-Data mode,
  FujiNet autonomously sends one private 2-MHz / nominal 2-us packet,
  IIgs validates the exact 512-byte payload.

There is no second manual PH0..PH3 trigger after the arm call.
Normal SmartPort remains unchanged at 1 MHz / 4 us.
'@ | Set-Content -LiteralPath $hostReadme -Encoding ASCII

& $cp2 create-disk-image $hostPo 32mb ProDOS
if ($LASTEXITCODE -ne 0) { throw 'cp2 create-disk-image failed.' }
& $cp2 rename $hostPo : FASTPROBE
if ($LASTEXITCODE -ne 0) { throw 'cp2 rename failed.' }
& $cp2 add --from-naps --strip-paths $hostPo $hostBin
if ($LASTEXITCODE -ne 0) { throw 'cp2 add FASTPROBE failed.' }
& $cp2 add --from-naps --strip-paths $hostPo $hostReadme
if ($LASTEXITCODE -ne 0) { throw 'cp2 add README failed.' }
& $cp2 test $hostPo
if ($LASTEXITCODE -ne 0) { throw 'cp2 filesystem test failed.' }

Write-Host 'P0.2C3 host image PASS.' -ForegroundColor Green

# ------------------------------------------------------------------
# Firmware build: P0.2C2 physical support -> delayed autosend overlay.
# ------------------------------------------------------------------
Push-Location $repoRoot
try {
    & $python.Source $patchC3Firmware `
        --project-root $repoRoot `
        --firmware-root $FirmwareRoot
    if ($LASTEXITCODE -ne 0) {
        throw 'FujiNet P0.2C3 firmware overlay failed.'
    }
}
finally {
    Pop-Location
}

$sampleIni = Join-Path $FirmwareRoot 'platformio-sample.ini'
$platformIni = Join-Path $FirmwareRoot 'platformio.ini'
$ini = Get-Content -LiteralPath $sampleIni -Raw

$replacements = @(
    @(';build_platform = BUILD_APPLE','build_platform = BUILD_APPLE'),
    @(';build_bus      = IWM','build_bus      = IWM'),
    @(
        ';build_board    = fujiapple-rev0         ; FujiApple Rev 0 Prototype',
        'build_board    = fujiapple-rev0         ; production Rev1 runtime detection'
    )
)

foreach ($pair in $replacements) {
    if ($ini.IndexOf($pair[0],[System.StringComparison]::Ordinal) -lt 0) {
        throw ('Missing platformio-sample pattern: ' + $pair[0])
    }
    $ini = $ini.Replace($pair[0],$pair[1])
}

$flagAnchor = '    -D DEBUG_SPEED=${env.monitor_speed}'
if ($ini.IndexOf($flagAnchor,[System.StringComparison]::Ordinal) -lt 0) {
    throw 'Unable to locate common build_flags block.'
}

$ini = $ini.Replace(
    $flagAnchor,
    $flagAnchor + [Environment]::NewLine + '    -D IIGS_FAST_IWM_PROBE'
)
Set-Content -LiteralPath $platformIni -Value $ini -Encoding ASCII

$forbidden = @(
    Select-String `
        -LiteralPath $platformIni `
        -Pattern '^[ \t]*-D[ \t]+(REV1DETECT|MASTERIES_REV0|MASTERIES_REVAB|NO3STATE)([ \t]|$)' `
        -CaseSensitive
)
if ($forbidden.Count -gt 0) {
    $forbidden | ForEach-Object { Write-Host $_.Line -ForegroundColor Red }
    throw 'Forbidden FujiApple hardware override is active.'
}

Push-Location $FirmwareRoot
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

$pioOut = Join-Path $FirmwareRoot '.pio\build\fujiapple-rev0'
$firmwareBin = Join-Path $pioOut 'firmware.bin'
$firmwareElf = Join-Path $pioOut 'firmware.elf'

if (-not (Test-Path -LiteralPath $firmwareBin -PathType Leaf)) {
    throw ('firmware.bin missing: ' + $firmwareBin)
}
if (-not (Test-Path -LiteralPath $firmwareElf -PathType Leaf)) {
    throw ('firmware.elf missing: ' + $firmwareElf)
}

$nm = Join-Path $env:USERPROFILE `
    '.platformio\packages\toolchain-xtensa-esp-elf\bin\xtensa-esp32-elf-nm.exe'
if (-not (Test-Path -LiteralPath $nm -PathType Leaf)) {
    throw ('xtensa nm tool missing: ' + $nm)
}

$nmLines = @(& $nm -C $firmwareElf)
if ($LASTEXITCODE -ne 0) {
    throw 'ELF symbol inspection failed.'
}

foreach ($symbol in @(
    'iwm_send_fast_probe_spi',
    'fast_iwm_probe_autosend_pending',
    'fast_iwm_probe_autosend_due_ms'
)) {
    if (@($nmLines | Where-Object { $_ -match $symbol }).Count -eq 0) {
        throw ('Required P0.2C3 symbol missing from firmware ELF: ' + $symbol)
    }
}

Write-Host 'P0.2C3 ELF symbol verification PASS.' -ForegroundColor Green

Copy-Item -LiteralPath $firmwareBin `
    -Destination (Join-Path $firmwareRelease 'fujinet-p0.2c3-firmware.bin') `
    -Force
Copy-Item -LiteralPath $firmwareElf `
    -Destination (Join-Path $firmwareRelease 'fujinet-p0.2c3-firmware.elf') `
    -Force
Copy-Item -LiteralPath $platformIni `
    -Destination (Join-Path $firmwareRelease 'platformio.production-rev1.ini') `
    -Force

@'
FujiNet P0.2C3 - delayed autonomous Fast-IWM transmit

Production Rev1 runtime detection.
REV1DETECT / MASTERIES_* / NO3STATE remain disabled.

Magic READBLOCK $7FA55A is handled normally at 4 us and returns a
synthetic $A5 block. Only after that response completes does FujiNet
schedule one private 2-MHz transmit 20 ms later. No second phase trigger
from the IIgs is required.

Expected serial diagnostics:
  FASTIWM C3 ARM block=7fa55a count=1
  FASTIWM C3 AUTO SCHEDULE delay=20ms
  FASTIWM C3 AUTO TX START ...
  FASTIWM C3 AUTO TX DONE ... err=0

Flash application only at 0x10000.
'@ | Set-Content `
    -LiteralPath (Join-Path $firmwareRelease 'README-P0.2C3.txt') `
    -Encoding ASCII

$hashLines = @()
Get-ChildItem -LiteralPath $releaseRoot -Recurse -File |
    Where-Object { $_.Name -ne 'SHA256SUMS.txt' } |
    Sort-Object FullName |
    ForEach-Object {
        $hash = Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256
        $relative = $_.FullName.Substring($releaseRoot.Length + 1)
        $hashLines += ($hash.Hash.ToLowerInvariant() + '  ' + $relative)
    }
$hashLines | Set-Content `
    -LiteralPath (Join-Path $releaseRoot 'SHA256SUMS.txt') `
    -Encoding ASCII

$zipPath = $releaseRoot + '.zip'
if (Test-Path -LiteralPath $zipPath) {
    Remove-Item -LiteralPath $zipPath -Force
}
Compress-Archive `
    -Path (Join-Path $releaseRoot '*') `
    -DestinationPath $zipPath `
    -CompressionLevel Optimal

$zipHash = Get-FileHash -LiteralPath $zipPath -Algorithm SHA256

Write-Host ''
Write-Host '=== P0.2C3 PAIRED BUILD COMPLETE ===' -ForegroundColor Green
Write-Host ('PO:       ' + $hostPo)
Write-Host ('Firmware: ' + (Join-Path $firmwareRelease 'fujinet-p0.2c3-firmware.bin'))
Write-Host ('ZIP:      ' + $zipPath)
Write-Host ('SHA256:   ' + $zipHash.Hash.ToLowerInvariant())
