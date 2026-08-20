#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$DevRoot = 'C:\AppleIIgsDev_02'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptRoot

$python = Get-Command python.exe -ErrorAction SilentlyContinue
if ($null -eq $python) { $python = Get-Command python -ErrorAction SilentlyContinue }
if ($null -eq $python) { throw 'Python is not available on PATH.' }

$patchB3 = Join-Path $repoRoot 'tools\patch_spbench_p01b3_v2.py'
$fixB3 = Join-Path $repoRoot 'tools\fix_spbench_p01b3_branches.py'
$patchC7 = Join-Path $repoRoot 'tools\patch_spbench_fastiwm_p02c7.py'
$fixC = Join-Path $repoRoot 'tools\fix_fastiwm_p02c_branches.py'
$baseBuilder = Join-Path $scriptRoot 'Build-SPBench-P01B.ps1'
$cp2 = Join-Path $DevRoot 'tools\cp2\cp2.exe'

foreach ($required in @($patchB3,$fixB3,$patchC7,$fixC,$baseBuilder,$cp2)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw ('Missing required build input: ' + $required)
    }
}

Write-Host ''
Write-Host '=== FASTPROBE P0.2C7 host-only build ===' -ForegroundColor Cyan
Write-Host 'KEEP FujiNet P0.2C4 delayed-autosend firmware.'
Write-Host 'New variable: IIgs IWM mode is explicitly switched to $0F (2us) for receive.'
Write-Host ''

Push-Location $repoRoot
try {
    & $python.Source $patchB3
    if ($LASTEXITCODE -ne 0) { throw 'SPBENCH P0.1B3 patch failed.' }

    & $python.Source $fixB3
    if ($LASTEXITCODE -ne 0) { throw 'SPBENCH P0.1B3 branch fix failed.' }

    & $python.Source $patchC7 --project-root $repoRoot
    if ($LASTEXITCODE -ne 0) { throw 'FASTPROBE P0.2C7 host patch failed.' }

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

$release = Join-Path $repoRoot 'build\fastiwm-p0.2c7-host'
if (Test-Path -LiteralPath $release) {
    Remove-Item -LiteralPath $release -Recurse -Force
}
New-Item -ItemType Directory -Path $release -Force | Out-Null

$fastBin = Join-Path $release 'FASTPROBE-P0.2C7#B30000'
$image = Join-Path $release 'FASTPROBE-P0.2C7.po'
$readme = Join-Path $release 'README-P0.2C7#040000'

Copy-Item -LiteralPath $sourceBin -Destination $fastBin -Force

@'
FASTPROBE P0.2C7 - IIgs IWM 2us receive mode

KEEP the already-flashed FujiNet P0.2C4 delayed-autosend firmware.
No FujiNet rebuild or reflash is required.

P0.2C4 proved FujiNet sends the 512-byte private packet at 2us cells.
P0.2C5 corrected DRIVE ENABLE / Read Data selection.
P0.2C6 removed post-arm TextTools and obsolete phase-trigger latency.

P0.2C7 fixes the remaining IIgs-side timing mismatch:
  - save the current IWM mode from Status;
  - drive off and program IWM mode $0F;
  - verify mode bits 0..4 through Status;
  - enable Read Data and receive the 2us packet;
  - reset the bus, restore the prior IWM mode, and restore IIgs Speed.

Mode $0F is the documented IIgs/3.5-inch setting with the IWM C bit set,
selecting a 2us bit cell rather than the normal SmartPort/5.25-inch 4us cell.
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
foreach ($name in @('FASTPROBE-P0.2C7#B30000','FASTPROBE-P0.2C7.po')) {
    $path = Join-Path $release $name
    $hash = Get-FileHash -LiteralPath $path -Algorithm SHA256
    $hashLines += ($hash.Hash.ToLowerInvariant() + '  ' + $name)
}
$hashLines | Set-Content -LiteralPath (Join-Path $release 'SHA256SUMS.txt') -Encoding ASCII

Write-Host ''
Write-Host 'FASTPROBE P0.2C7 HOST BUILD COMPLETE' -ForegroundColor Green
Write-Host ('PO: ' + $image)
Write-Host 'FujiNet: KEEP P0.2C4 firmware.' -ForegroundColor Green
