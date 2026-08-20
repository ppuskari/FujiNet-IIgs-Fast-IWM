#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$DevRoot = 'C:\AppleIIgsDev_02',
    [switch]$OpenOutputFolder
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0

$thisScript = $MyInvocation.MyCommand.Path
if ([string]::IsNullOrWhiteSpace($thisScript)) {
    throw 'Unable to determine build script path.'
}

$scriptRoot = Split-Path -Parent $thisScript
$repoRoot = Split-Path -Parent $scriptRoot
$sourceRoot = Join-Path $repoRoot 'iigs\fastprobe\src'
$buildRoot = Join-Path $repoRoot 'build\fastprobe-p0.2b'
$releaseRoot = Join-Path $buildRoot 'release'

$merlin = Join-Path $DevRoot 'tools\Merlin32_v1.2_b2\Windows\Merlin32.exe'
$library = Join-Path $DevRoot 'tools\Merlin32_v1.2_b2\Library'
$cp2 = Join-Path $DevRoot 'tools\cp2\cp2.exe'

foreach ($required in @($merlin, $cp2)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw ('Missing required tool: ' + $required)
    }
}
if (-not (Test-Path -LiteralPath $library -PathType Container)) {
    throw ('Missing Merlin32 library: ' + $library)
}

if (Test-Path -LiteralPath $buildRoot) {
    Remove-Item -LiteralPath $buildRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $releaseRoot -Force | Out-Null

Write-Host 'FASTPROBE P0.2B build'
Write-Host ('Source: ' + $sourceRoot)
Write-Host ('Output: ' + $releaseRoot)
Write-Host ''

Push-Location $sourceRoot
try {
    Remove-Item -LiteralPath '.\FASTPROBE' -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath '.\FASTPROBE_Output.txt' -Force -ErrorAction SilentlyContinue

    & $merlin -V $library 'fastprobe.make.s'
    $asmExit = $LASTEXITCODE
    if ($asmExit -ne 0) {
        throw ('Merlin32 failed with exit code ' + $asmExit)
    }

    if (-not (Test-Path -LiteralPath '.\FASTPROBE' -PathType Leaf)) {
        throw 'Merlin32 did not produce FASTPROBE.'
    }

    Copy-Item -LiteralPath '.\FASTPROBE' `
        -Destination (Join-Path $releaseRoot 'FASTPROBE#B30000') -Force

    if (Test-Path -LiteralPath '.\FASTPROBE_Output.txt' -PathType Leaf) {
        Copy-Item -LiteralPath '.\FASTPROBE_Output.txt' `
            -Destination (Join-Path $releaseRoot 'FASTPROBE_Output.txt') -Force
    }
}
finally {
    Pop-Location
}

$readmePath = Join-Path $releaseRoot 'README#040000'
@'
FASTPROBE P0.2B - Apple IIgs / FujiNet private Fast-IWM wire test

REQUIRES the matching experimental FujiNet P0.2B firmware responder.
Do not expect this program to work with ordinary FujiNet firmware.

The fast transfer does not call ROM SmartPort. It uses a private phase
signature, FujiNet ACK, and direct IWM read-data polling while the IIgs is
in its observed idle fast mode. The first packet is pattern-verified; a
256-packet run then reports raw 512-byte stream throughput.

The program pulses the SmartPort reset phase pattern before returning.
'@ | Set-Content -LiteralPath $readmePath -Encoding ASCII

$image = Join-Path $releaseRoot 'FASTPROBE-P0.2B.po'

& $cp2 create-disk-image $image 32mb ProDOS
if ($LASTEXITCODE -ne 0) { throw 'cp2 create-disk-image failed.' }
& $cp2 rename $image : FASTPROBE
if ($LASTEXITCODE -ne 0) { throw 'cp2 rename failed.' }
& $cp2 add --from-naps --strip-paths $image `
    (Join-Path $releaseRoot 'FASTPROBE#B30000')
if ($LASTEXITCODE -ne 0) { throw 'cp2 add FASTPROBE failed.' }
& $cp2 add --from-naps --strip-paths $image $readmePath
if ($LASTEXITCODE -ne 0) { throw 'cp2 add README failed.' }

$catalogPath = Join-Path $releaseRoot 'FASTPROBE-P0.2B.catalog.txt'
$catalogLines = @(& $cp2 catalog --depth=max --wide $image)
if ($LASTEXITCODE -ne 0) { throw 'cp2 catalog failed.' }
$catalogLines | Set-Content -LiteralPath $catalogPath -Encoding ASCII
$catalogLines | ForEach-Object { Write-Host $_ }

& $cp2 test $image
if ($LASTEXITCODE -ne 0) { throw 'cp2 test failed.' }

$hashLines = @()
foreach ($fileName in @('FASTPROBE#B30000', 'FASTPROBE-P0.2B.po')) {
    $fullPath = Join-Path $releaseRoot $fileName
    $hash = Get-FileHash -LiteralPath $fullPath -Algorithm SHA256
    $hashLines += ($hash.Hash.ToLowerInvariant() + '  ' + $fileName)
}
$hashLines | Set-Content `
    -LiteralPath (Join-Path $releaseRoot 'SHA256SUMS.txt') `
    -Encoding ASCII

Write-Host ''
Write-Host 'FASTPROBE P0.2B BUILD COMPLETE' -ForegroundColor Green
Write-Host ('Image: ' + $image)

if ($OpenOutputFolder) {
    Start-Process explorer.exe -ArgumentList $releaseRoot
}
