[CmdletBinding()]
param([switch]$Reload)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root 'backend\.venv\Scripts\python.exe'
if (-not (Test-Path $Python)) { throw 'Backend environment is missing. Run .\scripts\setup.ps1 first.' }
Push-Location (Join-Path $Root 'backend')
try {
    & $Python -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw 'Database migration failed.' }

    # Background startup must not leave Uvicorn's reload child behind. Developers
    # can still opt in explicitly with .\scripts\start-backend.ps1 -Reload.
    $env:APP_DEBUG = if ($Reload) { 'true' } else { 'false' }
    & $Python -m app.run
} finally { Pop-Location }

