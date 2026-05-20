$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    Write-Host "Creating virtual environment..."
    python -m venv (Join-Path $ProjectRoot ".venv")
}

if (-not (Test-Path $Python)) {
    Write-Error "Could not find Python in .venv. Install Python 3.10+ and try again."
}

Write-Host "Installing required packages..."
& $Python -m pip install -r (Join-Path $ProjectRoot "requirements.txt")

Write-Host "Starting ShoeScraper frontend..."
& $Python (Join-Path $ProjectRoot "web_app.py")
