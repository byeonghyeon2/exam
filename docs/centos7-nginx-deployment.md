# CentOS 7 + Nginx deployment

The production browser uses the same origin for the React application and API. Nginx serves the Vite bundle from `/usr/share/nginx/html/exam` and proxies `/api/v1/*` to FastAPI on `127.0.0.1:8000`.

## Frontend

Create `frontend/.env.production` on the server. This file is ignored by Git.

```dotenv
VITE_API_BASE_URL=/api/v1
```

Build and deploy the static files. Vite environment variables are compiled at build time, so rebuild whenever they change.

```bash
cd frontend
npm ci
npm run build
sudo rsync -a --delete dist/ /usr/share/nginx/html/exam/
```

Do not put database credentials, OpenAI keys, or authentication secrets in any `VITE_*` variable.

## Backend

Copy `backend/.env.production.example` to `backend/.env`, replace every placeholder, and keep the file outside Git. For the current HTTP deployment use:

```dotenv
APP_ENV=production
APP_HOST=127.0.0.1
APP_PORT=8000
APP_DEBUG=false
FRONTEND_ORIGIN=http://your-public-host
CORS_ALLOW_LOCAL_NETWORK=false
PROXY_TRUSTED_IPS=127.0.0.1
AUTH_COOKIE_SECURE=false
```

After HTTPS is enabled, change `FRONTEND_ORIGIN` to the final `https://` URL and set `AUTH_COOKIE_SECURE=true` before restarting the backend.

Install `deploy/systemd/exam-backend.service.example` as a systemd unit after replacing `/opt/exam` and the service account with the real deployment path and user.

## Nginx

Install `deploy/nginx/exam.conf.example` as an Nginx server configuration. The `proxy_pass` intentionally has no trailing path, so `/api/v1` is preserved when FastAPI receives the request. The SPA fallback must remain under `location /` so API failures are never replaced with `index.html`.

Validate before reload:

```bash
sudo nginx -t
sudo systemctl daemon-reload
sudo systemctl enable --now exam-backend
sudo systemctl reload nginx
curl http://127.0.0.1:8000/api/v1/health
curl http://your-public-host/api/v1/health
```

FastAPI port 8000 should not be forwarded by the router or opened to the internet.
