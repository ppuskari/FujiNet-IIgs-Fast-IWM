#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$DevRoot = 'C:\AppleIIgsDev_02',
    [switch]$OpenOutputFolder
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0

# Resolve paths at runtime.  Do not use $PSScriptRoot in a
# param() default expression; this script is intentionally kept
# compatible with Windows PowerShell 5.1.
$thisScript = $MyInvocation.MyCommand.Path
if ([string]::IsNullOrWhiteSpace($thisScript)) {
    throw 'Unable to determine build script path.'
}

$scriptRoot = Split-Path -Parent $thisScript
$repoRoot = Split-Path -Parent $scriptRoot
$devRootFull = [IO.Path]::GetFullPath($DevRoot)

$sourceRoot = Join-Path $repoRoot 'iigs\spbench\src'
$buildRoot = Join-Path $repoRoot 'build\spbench-p0.1a'
$releaseRoot = Join-Path $buildRoot 'release'
$logRoot = Join-Path $buildRoot 'logs'

$merlin32 = Join-Path $devRootFull `
    'tools\Merlin32_v1.2_b2\Windows\Merlin32.exe'
$merlinLibrary = Join-Path $devRootFull `
    'tools\Merlin32_v1.2_b2\Library'
$cp2 = Join-Path $devRootFull 'tools\cp2\cp2.exe'

$makeFile = Join-Path $sourceRoot 'spbench.make.s'
$sourceFile = Join-Path $sourceRoot 'SPBench.s'
$assembledFile = Join-Path $sourceRoot 'SPBENCH'
$linkFile = Join-Path $sourceRoot 'SPBENCH.L'

$napsBinary = Join-Path $releaseRoot 'SPBENCH#B30000'
$imagePath = Join-Path $releaseRoot 'SPBENCH-P0.1A.po'
$catalogPath = Join-Path $releaseRoot 'SPBENCH-P0.1A.catalog.txt'
$readmeNaps = Join-Path $releaseRoot 'README#040000'
$buildInfo = Join-Path $releaseRoot 'BUILD-INFO.txt'
$merlinLog = Join-Path $logRoot 'merlin32.log'
$finalZip = Join-Path $buildRoot 'SPBENCH-P0.1A.zip'

function Write-Section {
    param([string]$Text)
    Write-Host ''
    Write-Host ('==== ' + $Text + ' ====') -ForegroundColor Cyan
}

function Assert-File {
    param(
        [string]$Path,
        [string]$Description
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw ('Missing ' + $Description + ': ' + $Path)
    }
}

function Assert-Directory {
    param(
        [string]$Path,
        [string]$Description
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
        throw ('Missing ' + $Description + ': ' + $Path)
    }
}

function Get-Sha256 {
    param([string]$Path)

    return (
        Get-FileHash -LiteralPath $Path -Algorithm SHA256
    ).Hash.ToLowerInvariant()
}

function Invoke-NativeChecked {
    param(
        [string]$FilePath,
        [object[]]$Arguments,
        [string]$Description,
        [string]$WorkingDirectory = ''
    )

    $savedPreference = $ErrorActionPreference

    try {
        $ErrorActionPreference = 'Continue'

        if ([string]::IsNullOrWhiteSpace($WorkingDirectory)) {
            $lines = @(& $FilePath @Arguments 2>&1)
            $exitCode = $LASTEXITCODE
        }
        else {
            Push-Location $WorkingDirectory
            try {
                $lines = @(& $FilePath @Arguments 2>&1)
                $exitCode = $LASTEXITCODE
            }
            finally {
                Pop-Location
            }
        }
    }
    finally {
        $ErrorActionPreference = $savedPreference
    }

    foreach ($line in $lines) {
        Write-Host ([string]$line)
    }

    if ($exitCode -ne 0) {
        throw (
            $Description +
            ' failed with exit code ' +
            $exitCode
        )
    }

    return $lines
}

Write-Host 'SPBENCH P0.1A build'
Write-Host ('Repository: ' + $repoRoot)
Write-Host ('Dev root:   ' + $devRootFull)

Write-Section 'Validate tools and source'
Assert-File $merlin32 'Merlin32 executable'
Assert-Directory $merlinLibrary 'Merlin32 library'
Assert-File $cp2 'CiderPress II cp2 executable'
Assert-File $sourceFile 'SPBENCH source'
Assert-File $makeFile 'SPBENCH Merlin make file'

Write-Section 'Prepare build directories'
Remove-Item -LiteralPath $buildRoot `
    -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $releaseRoot -Force | Out-Null
New-Item -ItemType Directory -Path $logRoot -Force | Out-Null

Remove-Item -LiteralPath $assembledFile `
    -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $linkFile `
    -Force -ErrorAction SilentlyContinue

Write-Section 'Assemble SPBENCH with Merlin32'
$merlinLines = @(
    Invoke-NativeChecked `
        -FilePath $merlin32 `
        -Arguments @('-V', $merlinLibrary, 'spbench.make.s') `
        -Description 'Merlin32 assembly' `
        -WorkingDirectory $sourceRoot
)
$merlinLines | Set-Content -LiteralPath $merlinLog -Encoding UTF8

Assert-File $assembledFile 'assembled SPBENCH binary'
Copy-Item -LiteralPath $assembledFile `
    -Destination $napsBinary -Force

Write-Section 'Create FujiNet deployment image'
Invoke-NativeChecked `
    -FilePath $cp2 `
    -Arguments @('create-disk-image', $imagePath, '32mb', 'ProDOS') `
    -Description 'cp2 create-disk-image' | Out-Null

Invoke-NativeChecked `
    -FilePath $cp2 `
    -Arguments @('rename', $imagePath, ':', 'SPBENCH') `
    -Description 'cp2 rename' | Out-Null

Invoke-NativeChecked `
    -FilePath $cp2 `
    -Arguments @(
        'add',
        '--from-naps',
        '--strip-paths',
        $imagePath,
        $napsBinary
    ) `
    -Description 'cp2 add SPBENCH' | Out-Null

@(
    'SPBENCH P0.1A - GS/OS DRead baseline',
    '',
    'Mount this 32 MB ProDOS image on FujiNet.',
    'Launch SPBENCH from THIS volume.',
    '',
    'P0.1A identifies the GS/OS block device that owns prefix 1,',
    'then measures one 512-byte DRead call at a time.',
    '',
    'Sequence:',
    '  256 blocks / 128 KiB warm-up',
    '  2048 blocks / 1 MiB timed run',
    '  8192 blocks / 4 MiB timed run',
    '',
    'Record the complete screen output for both stock 2.8 MHz and',
    'accelerated IIgs testing.',
    '',
    'This is intentionally the GS/OS Device Manager baseline.',
    'P0.1B will move underneath GS/OS to direct SmartPort calls.'
) | Set-Content -LiteralPath $readmeNaps -Encoding ASCII

Invoke-NativeChecked `
    -FilePath $cp2 `
    -Arguments @(
        'add',
        '--from-naps',
        '--strip-paths',
        $imagePath,
        $readmeNaps
    ) `
    -Description 'cp2 add README' | Out-Null

Write-Section 'Catalog and validate image'
$catalogLines = @(
    Invoke-NativeChecked `
        -FilePath $cp2 `
        -Arguments @('catalog', '--depth=max', '--wide', $imagePath) `
        -Description 'cp2 catalog'
)
$catalogLines | Set-Content -LiteralPath $catalogPath -Encoding UTF8

Invoke-NativeChecked `
    -FilePath $cp2 `
    -Arguments @('test', $imagePath) `
    -Description 'cp2 filesystem test' | Out-Null

@(
    'SPBENCH P0.1A',
    ('BuiltLocal=' + (Get-Date).ToString('o')),
    ('SourceSHA256=' + (Get-Sha256 $sourceFile)),
    ('BinarySHA256=' + (Get-Sha256 $napsBinary)),
    ('ImageSHA256=' + (Get-Sha256 $imagePath)),
    ('Merlin32=' + $merlin32),
    ('MerlinLibrary=' + $merlinLibrary),
    ('cp2=' + $cp2)
) | Set-Content -LiteralPath $buildInfo -Encoding ASCII

Write-Section 'Create release ZIP'
Remove-Item -LiteralPath $finalZip -Force -ErrorAction SilentlyContinue
Compress-Archive `
    -Path (Join-Path $releaseRoot '*') `
    -DestinationPath $finalZip `
    -CompressionLevel Optimal

Write-Host ''
Write-Host 'BUILD COMPLETE' -ForegroundColor Green
Write-Host ('Binary: ' + $napsBinary)
Write-Host ('Image:  ' + $imagePath)
Write-Host ('ZIP:    ' + $finalZip)
Write-Host ('ZIP SHA256: ' + (Get-Sha256 $finalZip))

if ($OpenOutputFolder) {
    Start-Process explorer.exe -ArgumentList $releaseRoot
}
