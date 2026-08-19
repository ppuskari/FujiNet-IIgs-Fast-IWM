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
$sourceRoot = Join-Path $repoRoot 'iigs\iwmprobe\src'
$buildRoot = Join-Path $repoRoot 'build\iwmprobe-p0.2a'
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

Write-Host 'IWMPROBE P0.2A build'
Write-Host ('Source: ' + $sourceRoot)
Write-Host ('Output: ' + $releaseRoot)
Write-Host ''

Push-Location $sourceRoot
try {
    Remove-Item -LiteralPath '.\IWMPROBE' -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath '.\IWMPROBE_Output.txt' -Force -ErrorAction SilentlyContinue

    & $merlin -V $library 'iwmprobe.make.s'
    $asmExit = $LASTEXITCODE
    if ($asmExit -ne 0) {
        throw ('Merlin32 failed with exit code ' + $asmExit)
    }

    if (-not (Test-Path -LiteralPath '.\IWMPROBE' -PathType Leaf)) {
        throw 'Merlin32 did not produce IWMPROBE.'
    }

    Copy-Item -LiteralPath '.\IWMPROBE' `
        -Destination (Join-Path $releaseRoot 'IWMPROBE#B30000') -Force

    if (Test-Path -LiteralPath '.\IWMPROBE_Output.txt' -PathType Leaf) {
        Copy-Item -LiteralPath '.\IWMPROBE_Output.txt' `
            -Destination (Join-Path $releaseRoot 'IWMPROBE_Output.txt') -Force
    }
}
finally {
    Pop-Location
}

$readmePath = Join-Path $releaseRoot 'README#040000'
@'
IWMPROBE P0.2A - Apple IIgs IWM mode probe

This is a host-side mode-register probe only. It performs no disk I/O while
2 us mode is selected. It reads the initial IWM mode, waits for the motor-off
timer, sets bit 3, verifies it, then restores and verifies the original mode.

If the screen says RESTORE FAILED, reboot before accessing disks.
'@ | Set-Content -LiteralPath $readmePath -Encoding ASCII

$image = Join-Path $releaseRoot 'IWMPROBE-P0.2A.po'

& $cp2 create-disk-image $image 32mb ProDOS
if ($LASTEXITCODE -ne 0) { throw 'cp2 create-disk-image failed.' }
& $cp2 rename $image : IWMPROBE
if ($LASTEXITCODE -ne 0) { throw 'cp2 rename failed.' }
& $cp2 add --from-naps --strip-paths $image `
    (Join-Path $releaseRoot 'IWMPROBE#B30000')
if ($LASTEXITCODE -ne 0) { throw 'cp2 add IWMPROBE failed.' }
& $cp2 add --from-naps --strip-paths $image $readmePath
if ($LASTEXITCODE -ne 0) { throw 'cp2 add README failed.' }

$catalogPath = Join-Path $releaseRoot 'IWMPROBE-P0.2A.catalog.txt'
$catalogLines = @(& $cp2 catalog --depth=max --wide $image)
if ($LASTEXITCODE -ne 0) { throw 'cp2 catalog failed.' }
$catalogLines | Set-Content -LiteralPath $catalogPath -Encoding ASCII
$catalogLines | ForEach-Object { Write-Host $_ }

& $cp2 test $image
if ($LASTEXITCODE -ne 0) { throw 'cp2 test failed.' }

$hashLines = @()
foreach ($fileName in @('IWMPROBE#B30000', 'IWMPROBE-P0.2A.po')) {
    $fullPath = Join-Path $releaseRoot $fileName
    $hash = Get-FileHash -LiteralPath $fullPath -Algorithm SHA256
    $hashLines += ($hash.Hash.ToLowerInvariant() + '  ' + $fileName)
}
$hashLines | Set-Content `
    -LiteralPath (Join-Path $releaseRoot 'SHA256SUMS.txt') `
    -Encoding ASCII

Write-Host ''
Write-Host 'IWMPROBE P0.2A BUILD COMPLETE' -ForegroundColor Green
Write-Host ('Image: ' + $image)

if ($OpenOutputFolder) {
    Start-Process explorer.exe -ArgumentList $releaseRoot
}
