[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$State = Join-Path $Root '.run'
New-Item -ItemType Directory -Force -Path $State | Out-Null
$Backend = Start-Process powershell -WindowStyle Hidden -PassThru -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File',(Join-Path $PSScriptRoot 'start-backend.ps1'))
$Frontend = Start-Process powershell -WindowStyle Hidden -PassThru -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File',(Join-Path $PSScriptRoot 'start-frontend.ps1'))
@{ backend = $Backend.Id; frontend = $Frontend.Id } | ConvertTo-Json | Set-Content -Encoding utf8 (Join-Path $State 'processes.json')
Write-Host "Started backend PID $($Backend.Id) and frontend PID $($Frontend.Id)."

