# Git and deployment

Do not commit `.env`, imported source data, generated reports, database volumes, or API keys. Initialize and publish with:

```bash
git init
git add .
git commit -m "Initial certification exam app"
git branch -M main
git remote add origin <REMOTE_URL>
git push -u origin main
```

CI runs backend lint, type checks and tests plus frontend lint, type checks, tests and a production build. It uses no OpenAI secret and tests must use the fake AI adapter. For deployment, provide runtime secrets outside Git, run `alembic upgrade head`, and terminate TLS at a trusted reverse proxy.

For the current Ubuntu server, use [approved release deployment](ubuntu-approved-deployment.md).
Its installed `exam-deploy` command fetches main, reuses unchanged dependencies and builds an isolated release,
activates it and rolls back code/frontend on failed health checks.
It never runs Alembic automatically: a schema mismatch stops for separate review.
Full lint/type/test checks remain in GitHub CI, not repeated on the production server.
The command does not wait for CI; verify CI success before invoking deployment.
DB backups run only on the monthly timer (day 1, 03:20 Asia/Seoul plus existing jitter),
not during deployment. A successful backup retains the latest three verified backup sets.

