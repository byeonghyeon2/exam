[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Push-Location (Join-Path $Root 'frontend')
try { npm.cmd run dev -- --host 0.0.0.0 } finally { Pop-Location }

