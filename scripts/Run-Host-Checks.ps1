#requires -Version 5.1
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot

Push-Location $repoRoot
try {
    $py = Get-Command python -ErrorAction SilentlyContinue
    if (-not $py) { $py = Get-Command py -ErrorAction SilentlyContinue }
    if (-not $py) { throw 'Python was not found.' }

    if ($py.Name -eq 'py.exe' -or $py.Name -eq 'py') {
        & $py.Source -3 .\tools\throughput_model.py
        & $py.Source -3 -m pytest -q
    }
    else {
        & $py.Source .\tools\throughput_model.py
        & $py.Source -m pytest -q
    }
    if ($LASTEXITCODE) { throw "Host checks failed: $LASTEXITCODE" }
}
finally {
    Pop-Location
}
