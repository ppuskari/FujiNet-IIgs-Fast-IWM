#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$DevRoot = 'C:\AppleIIgsDev_02'
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
$patchC5 = Join-Path $repoRoot 'tools\patch_spbench_fastiwm_p02c5.py'
$fixC = Join-Path $repoRoot 'tools\fix_fastiwm_p02c_branches.py'
$baseBuilder = Join-Path $scriptRoot 'Build-SPBench-P01B.ps1'
$cp2 = Join-Path $DevRoot 'tools\cp2\cp2.exe'

foreach ($required in @($patchB3,$fixB3,$patchC5,$fixC,$baseBuilder,$cp2)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw ('Missing required build input: ' + $required)
    }
}

Write-Host ''
Write-Host '=== FASTPROBE P0.2C5 host-only build ===' -ForegroundColor Cyan
Write-Host 'P0.2C4 FujiNet firmware stays flashed.'
Write-Host 'Host now enables the IWM Read-Data state per Apple IIgs TN #30.'
Write-Host ''

Push-Location $repoRoot
try {
    & $python.Source $patchB3
    if ($LASTEXITCODE -ne 0) { throw 'SPBENCH P0.1B3 patch failed.' }

    & $python.Source $fixB3
    if ($LASTEXITCODE -ne 0) { throw 'SPBENCH P0.1B3 branch fix failed.' }

    & $python.Source $patchC5 --project-root $repoRoot
    if ($LASTEXITCODE -ne 0) { throw 'FASTPROBE P0.2C5 host patch failed.' }

    & $python.Source $fixC --project-root $repoRoot
    if ($LASTEXITCODE -ne 0) { throw 'FASTPROBE P0.2C branch fix failed.' }
}
finally {
    Pop-Location
}

& powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File $baseBuilder -DevRoot $DevRoot
if ($LASTEXITCODE -ne 0) {
    throw ('Underlying Merlin32 build failed with exit code ' + $LASTEXITCODE)
}

$sourceRelease = Join-Path $repoRoot 'build\spbench-p0.1b\release'
$sourceBin = Join-Path $sourceRelease 'SPBENCH#B30000'
if (-not (Test-Path -LiteralPath $sourceBin -PathType Leaf)) {
    throw ('Assembled S16 not found: ' + $sourceBin)
}

$release = Join-Path $repoRoot 'build\fastiwm-p0.2c5-host'
if (Test-Path -LiteralPath $release) {
    Remove-Item -LiteralPath $release -Recurse -Force
}
New-Item -ItemType Directory -Path $release -Force | Out-Null

$fastBin = Join-Path $release 'FASTPROBE-P0.2C5#B30000'
$image = Join-Path $release 'FASTPROBE-P0.2C5.po'
$readme = Join-Path $release 'README-P0.2C5#040000'

Copy-Item -LiteralPath $sourceBin -Destination $fastBin -Force

@'
FASTPROBE P0.2C5 - drive-enabled IWM Read-Data test

KEEP the already-flashed FujiNet P0.2C4 delayed-autosend firmware.
No FujiNet rebuild or reflash is required.

P0.2C4 proved:
  - IIgs sent magic READBLOCK $7FA55A correctly.
  - FujiNet armed correctly.
  - delayed 2-MHz transmit started and completed with err=0.
  - physical fast packet occupied about 9 ms.

P0.2C host bug:
  It selected Q7=0/Q6=0 but never asserted $C0E9 DRIVE ENABLE.

Apple IIgs Technical Note #30 corrects the Hardware Reference and states:
  Read Data = Q7=0, Q6=0, DRIVE ENABLED.

P0.2C5 therefore:
  - saves the IIgs Speed register,
  - clears only Slot-6 motor detector bit 2 so $C0E9 does not slow CPU,
  - asserts $C0E9 drive enable,
  - performs the existing direct 2-us read,
  - asserts $C0E8 drive disable on exit,
  - restores the exact Speed register value.
'@ | Set-Content -LiteralPath $readme -Encoding ASCII

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
foreach ($name in @('FASTPROBE-P0.2C5#B30000','FASTPROBE-P0.2C5.po')) {
    $path = Join-Path $release $name
    $hash = Get-FileHash -LiteralPath $path -Algorithm SHA256
    $hashLines += ($hash.Hash.ToLowerInvariant() + '  ' + $name)
}
$hashLines | Set-Content -LiteralPath (Join-Path $release 'SHA256SUMS.txt') -Encoding ASCII

Write-Host ''
Write-Host 'FASTPROBE P0.2C5 HOST BUILD COMPLETE' -ForegroundColor Green
Write-Host ('PO: ' + $image)
Write-Host 'FujiNet: KEEP P0.2C4 firmware.' -ForegroundColor Green
