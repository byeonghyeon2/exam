[CmdletBinding(SupportsShouldProcess, ConfirmImpact='High')]
param([switch]$Force)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root 'backend\.venv\Scripts\python.exe'
if (-not $Force -and -not $PSCmdlet.ShouldProcess('cert_exam database', 'Downgrade and reapply all Alembic migrations')) { exit 0 }
Push-Location (Join-Path $Root 'backend')
try {
    & $Python -m alembic downgrade base
    if ($LASTEXITCODE -ne 0) { throw 'Alembic downgrade failed.' }
    & $Python -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw 'Alembic upgrade failed.' }
} finally { Pop-Location }

