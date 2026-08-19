#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$DevRoot = 'C:\AppleIIgsDev_02'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Find-One {
    param([string[]]$Candidates)
    foreach ($candidate in $Candidates) {
        if ([string]::IsNullOrWhiteSpace($candidate)) { continue }
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
        $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($cmd) { return $cmd.Source }
    }
    return $null
}

$merlin = Find-One @(
    (Join-Path $DevRoot 'tools\Merlin32_v1.2_b2\Windows\Merlin32.exe'),
    (Join-Path $DevRoot 'Merlin32_v1.2_b2\Windows\Merlin32.exe'),
    'Merlin32.exe', 'Merlin32'
)
$cp2 = Find-One @(
    (Join-Path $DevRoot 'tools\cp2\cp2.exe'),
    (Join-Path $DevRoot 'cp2\cp2.exe'),
    'cp2.exe', 'cp2'
)
$git = Find-One @('git.exe', 'git')
$gh = Find-One @('gh.exe', 'gh')
$python = Find-One @('python.exe', 'python', 'py.exe', 'py')
$pio = Find-One @('pio.exe', 'pio', 'platformio.exe', 'platformio')

$macroCandidates = @(
    (Join-Path $DevRoot 'tools\Merlin32_v1.2_b2\Library'),
    (Join-Path $DevRoot 'Merlin32_v1.2_b2\Library')
)
$macros = $macroCandidates | Where-Object {
    Test-Path -LiteralPath $_ -PathType Container
} | Select-Object -First 1

$rows = @(
    [pscustomobject]@{ Tool='Git'; Required=$true; Path=$git },
    [pscustomobject]@{ Tool='GitHub CLI'; Required=$true; Path=$gh },
    [pscustomobject]@{ Tool='Python'; Required=$true; Path=$python },
    [pscustomobject]@{ Tool='Merlin32'; Required=$true; Path=$merlin },
    [pscustomobject]@{ Tool='Merlin32 Library'; Required=$true; Path=$macros },
    [pscustomobject]@{ Tool='cp2'; Required=$true; Path=$cp2 },
    [pscustomobject]@{ Tool='PlatformIO'; Required=$false; Path=$pio }
)

$rows | Format-Table -AutoSize

$missingRequired = @($rows | Where-Object { $_.Required -and -not $_.Path })
if ($missingRequired.Count) {
    throw ('Missing required tools: ' + (($missingRequired.Tool) -join ', '))
}

Write-Host ''
Write-Host 'Required host environment is present.' -ForegroundColor Green
if (-not $pio) {
    Write-Host 'PlatformIO is not yet present; it is needed when firmware builds begin.' -ForegroundColor Yellow
}
