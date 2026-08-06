[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root 'backend\.venv\Scripts\python.exe'
if (-not (Test-Path $Python)) { throw 'Backend environment is missing. Run .\scripts\setup.ps1 first.' }
Push-Location (Join-Path $Root 'backend')
try {
    & $Python -m alembic upgrade head
    & $Python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
} finally { Pop-Location }

