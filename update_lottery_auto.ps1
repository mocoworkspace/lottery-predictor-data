# update_lottery_auto.ps1
# Fetches lottery draw results from loto-life.net (no browser needed),
# generates lottery.json and pushes to GitHub Pages.
#
# Usage: powershell -ExecutionPolicy Bypass -File update_lottery_auto.ps1

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ProjectDir = "C:\workspace\lottery-predictor-data"

function Write-Step([string]$msg) { Write-Host "`n>>> $msg" -ForegroundColor Cyan }
function Write-OK([string]$msg)   { Write-Host "  [OK] $msg" -ForegroundColor Green }
function Write-Fail([string]$msg) { Write-Host "  [NG] $msg" -ForegroundColor Red }

# --- 1. Generate lottery.json ---
Write-Step "Step 1: Generating lottery.json..."
Set-Location $ProjectDir
python scripts/fetch_lottery.py
if ($LASTEXITCODE -ne 0) {
    Write-Fail "fetch_lottery.py failed."
    exit 1
}
Write-OK "lottery.json updated."

# --- 2. Git commit and push ---
Write-Step "Step 2: Committing and pushing to GitHub..."
git add lottery.json
git diff --staged --quiet
if ($LASTEXITCODE -ne 0) {
    $DateStr = Get-Date -Format 'yyyy-MM-dd'
    git commit -m "Update lottery data $DateStr (auto)"
    git push
    Write-OK "Pushed to GitHub."
} else {
    Write-OK "No changes (already up to date)."
}

Write-Host "`n===== Done =====" -ForegroundColor Green
