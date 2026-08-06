[CmdletBinding()]
param(
    [string]$CertificationCode = 'DEA-C01',
    [switch]$OnlyUnclassified,
    [switch]$ReportOnly
)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root 'backend\.venv\Scripts\python.exe'
if (-not (Test-Path $Python)) { throw 'Backend environment is missing. Run .\scripts\setup.ps1 first.' }
$Arguments = @('-m','app.classifiers.domain_classifier','--certification',$CertificationCode)
if ($OnlyUnclassified) { $Arguments += '--only-unclassified' }
if ($ReportOnly) { $Arguments += '--report-only' }
Push-Location (Join-Path $Root 'backend')
try {
    & $Python @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Domain classification failed with exit code $LASTEXITCODE." }
} finally { Pop-Location }
