#requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$Experiment,
    [Parameter(Mandatory=$true)][string]$Machine,
    [Parameter(Mandatory=$true)][string]$Timing
)

$repoRoot = Split-Path -Parent $PSScriptRoot
$date = Get-Date -Format 'yyyyMMdd'
$safeMachine = $Machine -replace '[^A-Za-z0-9.-]','-'
$safeTiming = $Timing -replace '[^A-Za-z0-9.-]','-'
$name = "$Experiment-$safeMachine-$safeTiming-$date.md"
$path = Join-Path (Join-Path $repoRoot 'results') $name

if (Test-Path $path) { throw "Result file already exists: $path" }

@"
# $Experiment - $Machine - $Timing

Date: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')

## Configuration

- IIgs ROM:
- CPU/accelerator:
- FujiNet hardware:
- FujiNet firmware commit:
- SmartPort device/unit:
- transport timing:

## Run

- blocks:
- payload bytes:
- elapsed ticks:
- payload bytes/sec:
- payload kbit/sec:
- errors/retries:
- integrity failures:

## Observations

"@ | Set-Content -LiteralPath $path -Encoding UTF8

Write-Host $path
