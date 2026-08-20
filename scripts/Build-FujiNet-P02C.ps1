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
if ($null -eq $python) { $python = Get-Command python -ErrorAction SilentlyContinue }
if ($null -eq $python) { throw 'Python is not available on PATH.' }

$patch = Join-Path $repoRoot 'tools\patch_fujinet_fastiwm_p02c.py'
if (-not (Test-Path -LiteralPath $patch -PathType Leaf)) {
    throw ('P0.2C firmware patch missing: ' + $patch)
}
if (-not (Test-Path -LiteralPath $FirmwareRoot -PathType Container)) {
    throw ('FujiNet firmware root missing: ' + $FirmwareRoot)
}

Write-Host ''
Write-Host '=== FujiNet P0.2C SmartPort-arm build ===' -ForegroundColor Cyan
Write-Host ('Firmware root: ' + $FirmwareRoot)
Write-Host ''

& $python.Source $patch `
    --project-root $repoRoot `
    --firmware-root $FirmwareRoot
if ($LASTEXITCODE -ne 0) {
    throw ('P0.2C firmware patch failed with exit code ' + $LASTEXITCODE)
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

$anchor = '    -D DEBUG_SPEED=${env.monitor_speed}'
if ($ini.IndexOf($anchor,[System.StringComparison]::Ordinal) -lt 0) {
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

Write-Host 'Production Rev1 runtime-detect configuration verified.' -ForegroundColor Green

& $python.Source -m platformio run -e fujiapple-rev0
$pioExit = $LASTEXITCODE
if ($pioExit -ne 0) {
    # Retry from the firmware directory if caller was elsewhere.
    Push-Location $FirmwareRoot
    try {
        & $python.Source -m platformio run -e fujiapple-rev0
        $pioExit = $LASTEXITCODE
    }
    finally { Pop-Location }
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
if ($LASTEXITCODE -ne 0) { throw 'ELF symbol inspection failed.' }
foreach ($symbol in @('iwm_send_fast_probe_spi','fast_iwm_probe_armed','fast_iwm_probe_request')) {
    if (@($nmLines | Where-Object { $_ -match $symbol }).Count -eq 0) {
        throw ('Required P0.2C symbol missing from firmware ELF: ' + $symbol)
    }
}
Write-Host 'P0.2C ELF symbol verification PASS.' -ForegroundColor Green

$release = Join-Path $repoRoot 'build\fastiwm-p0.2c-paired\fujinet'
if (Test-Path -LiteralPath $release) {
    Remove-Item -LiteralPath $release -Recurse -Force
}
New-Item -ItemType Directory -Path $release -Force | Out-Null
Copy-Item -LiteralPath $firmwareBin `
    -Destination (Join-Path $release 'fujinet-p0.2c-firmware.bin') -Force
Copy-Item -LiteralPath $firmwareElf `
    -Destination (Join-Path $release 'fujinet-p0.2c-firmware.elf') -Force
Copy-Item -LiteralPath $platformIni `
    -Destination (Join-Path $release 'platformio.production-rev1.ini') -Force

@'
FujiNet P0.2C - SmartPort-armed Fast-IWM

Production Rev1 runtime detection.
REV1DETECT / MASTERIES_* / NO3STATE remain disabled.

Standard READBLOCK $7FA55A arms one private packet and returns a normal
4-us dummy block. The next armed SmartPort enable transition 1011 is
intercepted before normal command receive and queues one 2-MHz packet.
Serial diagnostics print ARM / REQ / TX START / TX DONE.

Flash application only at 0x10000.
'@ | Set-Content -LiteralPath (Join-Path $release 'README-P0.2C.txt') -Encoding ASCII

$hashLines = @()
Get-ChildItem -LiteralPath $release -File |
    Sort-Object Name |
    ForEach-Object {
        $hash = Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256
        $hashLines += ($hash.Hash.ToLowerInvariant() + '  ' + $_.Name)
    }
$hashLines | Set-Content -LiteralPath (Join-Path $release 'SHA256SUMS.txt') -Encoding ASCII

Write-Host ''
Write-Host 'FUJINET P0.2C BUILD COMPLETE' -ForegroundColor Green
Write-Host ('Firmware: ' + (Join-Path $release 'fujinet-p0.2c-firmware.bin'))
