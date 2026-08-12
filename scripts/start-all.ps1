[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$State = Join-Path $Root '.run'
New-Item -ItemType Directory -Force -Path $State | Out-Null

# Some launchers inject both PATH and Path. Start-Process treats them as duplicate
# dictionary keys, so normalize them before creating the background processes.
$PathEntries = @(& cmd.exe /d /c set) | Where-Object { $_ -cmatch '^(PATH|Path)=' }
if ($PathEntries.Count -gt 1) {
    $PathValue = ($PathEntries[0] -split '=', 2)[1]
    [Environment]::SetEnvironmentVariable('Path', $null, 'Process')
    [Environment]::SetEnvironmentVariable('Path', $PathValue, 'Process')
}

$Backend = Start-Process powershell -WindowStyle Hidden -PassThru -WorkingDirectory $Root `
    -RedirectStandardOutput (Join-Path $State 'backend.out.log') `
    -RedirectStandardError (Join-Path $State 'backend.err.log') `
    -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File',('"' + (Join-Path $PSScriptRoot 'start-backend.ps1') + '"'))
$Frontend = Start-Process powershell -WindowStyle Hidden -PassThru -WorkingDirectory $Root `
    -RedirectStandardOutput (Join-Path $State 'frontend.out.log') `
    -RedirectStandardError (Join-Path $State 'frontend.err.log') `
    -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File',('"' + (Join-Path $PSScriptRoot 'start-frontend.ps1') + '"'))
@{ backend = $Backend.Id; frontend = $Frontend.Id } | ConvertTo-Json | Set-Content -Encoding utf8 (Join-Path $State 'processes.json')
Write-Host "Started backend PID $($Backend.Id) and frontend PID $($Frontend.Id)."

