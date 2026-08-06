[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$PidFile = Join-Path $Root '.run\processes.json'
if (-not (Test-Path $PidFile)) { Write-Host 'No managed processes are recorded.'; exit 0 }
$Processes = Get-Content -Raw $PidFile | ConvertFrom-Json
foreach ($ProcessId in @($Processes.backend, $Processes.frontend)) {
    if ($ProcessId -and (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue)) { Stop-Process -Id $ProcessId -Force }
}
Remove-Item -LiteralPath $PidFile
Write-Host 'Managed development processes stopped.'

