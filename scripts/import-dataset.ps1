[CmdletBinding()]
param(
    [string]$Path,
    [ValidateSet('dry-run','strict','partial')][string]$Mode = 'dry-run'
)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$DefaultDatasetPath = Join-Path $Root 'data\processed\dataset\aws-dea-c01'
if ([string]::IsNullOrWhiteSpace($Path)) { $Path = $DefaultDatasetPath }
$DatasetPath = (Resolve-Path -LiteralPath $Path).Path
$Python = Join-Path $Root 'backend\.venv\Scripts\python.exe'
if (-not (Test-Path $Python)) { throw 'Backend environment is missing. Run .\scripts\setup.ps1 first.' }
Push-Location (Join-Path $Root 'backend')
try {
    & $Python -m app.importers.dataset_importer --path $DatasetPath --mode $Mode
    if ($LASTEXITCODE -ne 0) { throw "Dataset import failed with exit code $LASTEXITCODE." }
} finally { Pop-Location }
