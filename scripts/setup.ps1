[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path (Join-Path $Root '.env'))) { Copy-Item (Join-Path $Root '.env.example') (Join-Path $Root '.env') }
if (-not (Get-Command python -ErrorAction SilentlyContinue)) { throw 'Python 3.12 is required.' }
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { throw 'Node.js and npm are required.' }
Push-Location (Join-Path $Root 'backend')
try {
    if (-not (Test-Path '.venv')) { python -m venv .venv }
    & '.\.venv\Scripts\python.exe' -m pip install --upgrade pip
    & '.\.venv\Scripts\python.exe' -m pip install -e '.[dev]'
} finally { Pop-Location }
Push-Location (Join-Path $Root 'frontend')
try { npm install } finally { Pop-Location }
Write-Host 'Setup complete. Configure .env, ensure MySQL is running, then run .\scripts\start-all.ps1.'

