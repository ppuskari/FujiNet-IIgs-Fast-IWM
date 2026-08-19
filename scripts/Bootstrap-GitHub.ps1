#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$Owner = 'ppuskari',
    [string]$Name = 'FujiNet-IIgs-Fast-IWM',
    [ValidateSet('public','private')]
    [string]$Visibility = 'public'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw 'git is not installed or not on PATH.'
}
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    throw 'GitHub CLI (gh) is not installed or not on PATH.'
}

gh auth status
$nativeExit = $LASTEXITCODE
if ($nativeExit -ne 0) {
    throw 'GitHub CLI is not authenticated. Run: gh auth login'
}

if (-not (Test-Path -LiteralPath (Join-Path $repoRoot '.git'))) {
    git init -b main
    $nativeExit = $LASTEXITCODE
    if ($nativeExit -ne 0) {
        throw "git init failed: $nativeExit"
    }
}

git config core.autocrlf false
$nativeExit = $LASTEXITCODE
if ($nativeExit -ne 0) {
    throw "git config failed: $nativeExit"
}

git add .
$nativeExit = $LASTEXITCODE
if ($nativeExit -ne 0) {
    throw "git add failed: $nativeExit"
}

# IMPORTANT:
# Do not pipe native git directly into Select-Object -First under Windows
# PowerShell 5.1. Select-Object closes the pipe after the first line and
# Git for Windows can report -1 even though git status was otherwise fine.
$statusLines = @(git status --porcelain=v1 -b)
$nativeExit = $LASTEXITCODE
if ($nativeExit -ne 0) {
    throw "git status failed: $nativeExit"
}

$statusHeader = $null
if ($statusLines.Count -gt 0) {
    $statusHeader = [string]$statusLines[0]
}

$hasHead = $true
if ($statusHeader -and
    $statusHeader -match '^## No commits yet on ') {
    $hasHead = $false
}

if (-not $hasHead) {
    git commit -m 'Initial Fast-IWM experiment scaffold'
    $nativeExit = $LASTEXITCODE
    if ($nativeExit -ne 0) {
        throw "git commit failed: $nativeExit"
    }
}
else {
    $dirtyLines = @(git status --porcelain)
    $nativeExit = $LASTEXITCODE
    if ($nativeExit -ne 0) {
        throw "git status --porcelain failed: $nativeExit"
    }

    if ($dirtyLines.Count -gt 0) {
        git commit -m 'Update Fast-IWM experiment scaffold'
        $nativeExit = $LASTEXITCODE
        if ($nativeExit -ne 0) {
            throw "git commit failed: $nativeExit"
        }
    }
}

$fullName = "$Owner/$Name"

$remoteLines = @(git remote)
$nativeExit = $LASTEXITCODE
if ($nativeExit -ne 0) {
    throw "git remote failed: $nativeExit"
}
$originExists = ($remoteLines -contains 'origin')

if (-not $originExists) {
    cmd.exe /d /c "gh repo view $fullName --json nameWithOwner >nul 2>nul"
    $repoExists = ($LASTEXITCODE -eq 0)

    if ($repoExists) {
        git remote add origin "https://github.com/$fullName.git"
        $nativeExit = $LASTEXITCODE
        if ($nativeExit -ne 0) {
            throw "git remote add failed: $nativeExit"
        }
    }
    else {
        gh repo create $fullName "--$Visibility" `
            --source . `
            --remote origin `
            --push `
            --description 'Apple IIgs FujiNet Fast-IWM transport and DOC streaming experiments'

        $nativeExit = $LASTEXITCODE
        if ($nativeExit -ne 0) {
            throw "gh repo create failed: $nativeExit"
        }

        Write-Host ''
        Write-Host "Created and pushed: https://github.com/$fullName" `
            -ForegroundColor Green
        exit 0
    }
}

git branch -M main
$nativeExit = $LASTEXITCODE
if ($nativeExit -ne 0) {
    throw "git branch failed: $nativeExit"
}

git push -u origin main
$nativeExit = $LASTEXITCODE
if ($nativeExit -ne 0) {
    throw "git push failed: $nativeExit"
}

Write-Host ''
Write-Host "Repository ready: https://github.com/$fullName" `
    -ForegroundColor Green
