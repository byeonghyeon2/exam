# Windows setup

Install Python 3.12, Node.js 22, npm, Git, and MySQL 8. Enable PowerShell script execution for the current process with `Set-ExecutionPolicy -Scope Process Bypass`, then run `Copy-Item .env.example .env` and `.\scripts\setup.ps1`. Create the database/account shown in the README, configure `.env`, and run `.\scripts\start-all.ps1`.

The process IDs are stored in `.run/processes.json`; `.\scripts\stop-all.ps1` stops only those processes. Paths are passed as arguments rather than interpolated into commands, so spaces are supported. `reset-db.ps1` is destructive and prompts unless `-Force` is supplied.

