#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$RepoRoot = '',
    [string]$Upstream = 'https://github.com/FujiNetWIFI/fujinet-firmware.git',
    [string]$Commit = 'b0a9483463c93ab61279d265467159c0d27c9f82',
    [string]$Branch = 'petar/iigs-fast-iwm-p0'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Invoke-GitChecked {
    param(
        [Parameter(Mandatory=$true)]
        [string[]]$Arguments
    )

    & git.exe @Arguments
    $exitCode = $LASTEXITCODE

    if ($exitCode -ne 0) {
        throw (
            'git failed with exit code ' +
            $exitCode +
            ': git ' +
            ($Arguments -join ' ')
        )
    }
}

# Resolve the repository root at runtime. Do not use the automatic
# script-root variable in the param() default expression; on Windows
# PowerShell 5.1 it can evaluate before that variable is populated.
if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $thisScript = $MyInvocation.MyCommand.Path

    if ([string]::IsNullOrWhiteSpace($thisScript)) {
        throw 'Unable to determine the current script path.'
    }

    $scriptDirectory = Split-Path -Parent $thisScript

    if ([string]::IsNullOrWhiteSpace($scriptDirectory)) {
        throw 'Unable to determine the scripts directory.'
    }

    $RepoRoot = Split-Path -Parent $scriptDirectory
}

if (-not (Test-Path -LiteralPath $RepoRoot -PathType Container)) {
    throw 'Repository root not found: ' + $RepoRoot
}

if (-not (Get-Command git.exe -ErrorAction SilentlyContinue)) {
    throw 'git.exe is not installed or not available on PATH.'
}

$workRoot = Join-Path $RepoRoot 'work'
$fwRoot = Join-Path $workRoot 'fujinet-firmware'

New-Item `
    -ItemType Directory `
    -Path $workRoot `
    -Force | Out-Null

if (-not (Test-Path -LiteralPath $fwRoot -PathType Container)) {
    Write-Host 'Cloning FujiNet firmware...' -ForegroundColor Cyan

    Invoke-GitChecked -Arguments @(
        'clone',
        $Upstream,
        $fwRoot
    )
}

Push-Location $fwRoot

try {
    Write-Host 'Fetching FujiNet upstream...' -ForegroundColor Cyan

    Invoke-GitChecked -Arguments @(
        'fetch',
        'origin'
    )

    & git.exe cat-file -e ($Commit + '^{commit}')
    $commitCheckExit = $LASTEXITCODE

    if ($commitCheckExit -ne 0) {
        throw 'Pinned FujiNet commit is unavailable: ' + $Commit
    }

    & git.exe show-ref --verify --quiet ('refs/heads/' + $Branch)
    $branchCheckExit = $LASTEXITCODE

    if ($branchCheckExit -eq 0) {
        Write-Host (
            'Existing experiment branch found; preserving its current history: ' +
            $Branch
        ) -ForegroundColor Yellow

        Invoke-GitChecked -Arguments @(
            'checkout',
            $Branch
        )
    }
    elseif ($branchCheckExit -eq 1) {
        Write-Host (
            'Creating experiment branch at pinned FujiNet baseline: ' +
            $Branch
        ) -ForegroundColor Cyan

        Invoke-GitChecked -Arguments @(
            'checkout',
            '-b',
            $Branch,
            $Commit
        )
    }
    else {
        throw (
            'git show-ref failed with exit code ' +
            $branchCheckExit
        )
    }

    Write-Host ''
    Write-Host 'FujiNet firmware status:' -ForegroundColor Cyan

    & git.exe status -sb
    $statusExit = $LASTEXITCODE
    if ($statusExit -ne 0) {
        throw 'git status failed with exit code ' + $statusExit
    }

    & git.exe log -1 --oneline
    $logExit = $LASTEXITCODE
    if ($logExit -ne 0) {
        throw 'git log failed with exit code ' + $logExit
    }

    # Record the pinned baseline without resetting an existing experiment
    # branch. This makes rerunning the setup script safe after development
    # has started.
    $baselineFile = Join-Path $workRoot 'FUJINET-BASELINE.txt'
    Set-Content `
        -LiteralPath $baselineFile `
        -Value @(
            'Upstream=' + $Upstream,
            'PinnedCommit=' + $Commit,
            'ExperimentBranch=' + $Branch
        ) `
        -Encoding ASCII
}
finally {
    Pop-Location
}

Write-Host ''
Write-Host (
    'FujiNet experiment worktree ready: ' +
    $fwRoot
) -ForegroundColor Green
