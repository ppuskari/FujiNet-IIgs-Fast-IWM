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
$patchC = Join-Path $repoRoot 'tools\run_spbench_fastiwm_p02c.py'
$fixC = Join-Path $repoRoot 'tools\fix_fastiwm_p02c_branches.py'
$baseBuilder = Join-Path $scriptRoot 'Build-SPBench-P01B.ps1'
$cp2 = Join-Path $DevRoot 'tools\cp2\cp2.exe'

foreach ($required in @($patchB3,$fixB3,$patchC,$fixC,$baseBuilder,$cp2)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw ('Missing required build input: ' + $required)
    }
}

Write-Host ''
Write-Host '=== FASTPROBE P0.2C host build ===' -ForegroundColor Cyan
Write-Host 'Standard SmartPort B3 arm + normal 1010/1011 fast trigger.'
Write-Host ''

Push-Location $repoRoot
try {
    & $python.Source $patchB3
    if ($LASTEXITCODE -ne 0) { throw 'SPBENCH P0.1B3 patch failed.' }

    & $python.Source $fixB3
    if ($LASTEXITCODE -ne 0) { throw 'SPBENCH P0.1B3 branch fix failed.' }

    & $python.Source $patchC --project-root $repoRoot
    if ($LASTEXITCODE -ne 0) { throw 'FASTPROBE P0.2C host patch failed.' }

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

$release = Join-Path $repoRoot 'build\fastiwm-p0.2c-paired\host'
if (Test-Path -LiteralPath $release) {
    Remove-Item -LiteralPath $release -Recurse -Force
}
New-Item -ItemType Directory -Path $release -Force | Out-Null

$fastBin = Join-Path $release 'FASTPROBE#B30000'
$image = Join-Path $release 'FASTPROBE-P0.2C.po'
$readme = Join-Path $release 'README#040000'

Copy-Item -LiteralPath $sourceBin -Destination $fastBin -Force

@'
FASTPROBE P0.2C - SmartPort-armed Fast-IWM test

Requires matching FujiNet P0.2C firmware.

Sequence:
  standard SmartPort READBLOCK $7FA55A arms FujiNet at 4 us,
  ROM call returns normally,
  host drives proven SmartPort enable 1010 -> 1011,
  FujiNet emits one private 2-MHz / nominal 2-us packet,
  host validates exact 512-byte payload.

Normal SmartPort remains unchanged at 1 MHz / 4 us.
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
foreach ($name in @('FASTPROBE#B30000','FASTPROBE-P0.2C.po')) {
    $path = Join-Path $release $name
    $hash = Get-FileHash -LiteralPath $path -Algorithm SHA256
    $hashLines += ($hash.Hash.ToLowerInvariant() + '  ' + $name)
}
$hashLines | Set-Content -LiteralPath (Join-Path $release 'SHA256SUMS.txt') -Encoding ASCII

Write-Host ''
Write-Host 'FASTPROBE P0.2C HOST BUILD COMPLETE' -ForegroundColor Green
Write-Host ('PO: ' + $image)
