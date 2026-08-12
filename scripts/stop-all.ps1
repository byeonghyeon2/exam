[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$PidFile = Join-Path $Root '.run\processes.json'

function Stop-ManagedProcess([int]$ProcessId) {
    if (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue) {
        Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
    }
}

$Processes = $null
if (Test-Path $PidFile) {
    $Processes = Get-Content -Raw $PidFile | ConvertFrom-Json
    foreach ($ProcessId in @($Processes.backend, $Processes.frontend)) {
        if ($ProcessId) { Stop-ManagedProcess $ProcessId }
    }
    Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
}

# A crashed launcher or Uvicorn reload process can outlive its recorded parent.
# Stop only listeners on the development ports owned by this local stack.
foreach ($Port in @(8000, 5173)) {
    $Listeners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    foreach ($Listener in $Listeners) { Stop-ManagedProcess $Listener.OwningProcess }
}
Write-Host 'Managed development processes stopped.'

