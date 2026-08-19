#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$Upstream = 'https://github.com/FujiNetWIFI/fujinet-firmware.git',
    [string]$Commit = 'b0a9483463c93ab61279d265467159c0d27c9f82',
    [string]$Branch = 'petar/iigs-fast-iwm-p0'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$workRoot = Join-Path $RepoRoot 'work'
$fwRoot = Join-Path $workRoot 'fujinet-firmware'
New-Item -ItemType Directory -Path $workRoot -Force | Out-Null

if (-not (Test-Path -LiteralPath $fwRoot -PathType Container)) {
    git clone $Upstream $fwRoot
    if ($LASTEXITCODE) { throw "git clone failed: $LASTEXITCODE" }
}

Push-Location $fwRoot
try {
    git fetch origin
    if ($LASTEXITCODE) { throw "git fetch failed: $LASTEXITCODE" }

    git checkout --detach $Commit
    if ($LASTEXITCODE) { throw "checkout failed: $LASTEXITCODE" }

    $existing = git branch --list $Branch
    if ($existing) {
        git checkout $Branch
    }
    else {
        git checkout -b $Branch
    }
    if ($LASTEXITCODE) { throw "branch setup failed: $LASTEXITCODE" }

    Write-Host ''
    git status -sb
    git log -1 --oneline
}
finally {
    Pop-Location
}

Write-Host ''
Write-Host "FujiNet experiment worktree ready: $fwRoot" -ForegroundColor Green
