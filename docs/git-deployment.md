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

