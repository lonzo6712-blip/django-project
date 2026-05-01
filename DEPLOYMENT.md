# MonetteFarms Production Deployment

## Required production settings

Set these environment variables before starting the app:

```env
DJANGO_ENV=production
DJANGO_DEBUG=false
DJANGO_SECRET_KEY=replace-with-a-long-random-secret
DJANGO_ALLOWED_HOSTS=your-domain.example
DJANGO_CSRF_TRUSTED_ORIGINS=https://your-domain.example
DATABASE_URL=postgres://dbuser:dbpassword@dbhost:5432/dbname
CACHE_URL=redis://127.0.0.1:6379/1
DJANGO_LOG_LEVEL=INFO
SMS_BACKEND=checkins.sms.TwilioSMSBackend
SMS_FROM_NUMBER=+15550000000
SMS_TWILIO_ACCOUNT_SID=replace-with-twilio-account-sid
SMS_TWILIO_AUTH_TOKEN=replace-with-twilio-auth-token
SMS_RATE_LIMIT_SECONDS=30
DRIVER_CHECKIN_RATE_LIMIT_SECONDS=60
SMS_MAX_ATTEMPTS=5
SMS_RETRY_BASE_SECONDS=30
SMS_WORKER_POLL_SECONDS=5
SMS_WORKER_HEARTBEAT_TTL=60
UVICORN_HOST=0.0.0.0
UVICORN_PORT=8000
UVICORN_RELOAD=false
UVICORN_FORWARDED_ALLOW_IPS=127.0.0.1
```

## One-time setup

1. Install dependencies from `requirements.txt`.
2. Provision PostgreSQL and set `DATABASE_URL`.
3. Provision Redis and set `CACHE_URL`.
4. Run migrations:

```powershell
.\.venv\Scripts\python.exe manage.py migrate
```

5. Collect static files:

```powershell
.\.venv\Scripts\python.exe manage.py collectstatic --noinput
```

6. Create a staff or superuser account:

```powershell
.\.venv\Scripts\python.exe manage.py createsuperuser
```

## Render deployment

Use these settings for the current Render deployment at `django-project-1-g31l.onrender.com`.

This repo now includes a root-level `render.yaml` Blueprint with:
- `autoDeployTrigger: commit`
- `preDeployCommand: python manage.py migrate`
- `healthCheckPath: /healthz/`

Important:
- A `render.yaml` file only controls services that are actually managed by a Render Blueprint.
- If your current web service was created manually in the Render dashboard, adding `render.yaml` to the repo does not automatically change that existing service.
- To have Render apply the Blueprint settings, you need to create or sync a Blueprint in Render and map it to the intended service.

- Build command:

```bash
pip install -r requirements.txt && python manage.py migrate && python manage.py collectstatic --noinput
```

- Start command:

```bash
python run_asgi.py
```

- Recommended Render pre-deploy command:

```bash
python manage.py migrate
```

- Required Render environment variables:
  - `DJANGO_ENV=production`
  - `DJANGO_DEBUG=false`
  - `DJANGO_SECRET_KEY=<real secret>`
  - `DJANGO_ALLOWED_HOSTS=django-project-1-g31l.onrender.com`
  - `DJANGO_CSRF_TRUSTED_ORIGINS=https://django-project-1-g31l.onrender.com`
  - `DATABASE_URL=<Render Postgres internal or external URL>`
  - `CACHE_URL=<Render Redis internal or external URL>`

Notes:

- Do not use the placeholder values from `.env.production` for `DJANGO_SECRET_KEY`, `DATABASE_URL`, or Twilio credentials.
- Do not use `redis://127.0.0.1:6379/1` on Render unless Redis is actually running in the same container, which is not the normal Render setup.
- Run `python manage.py migrate` after provisioning the database and before serving live traffic.
- If the Render deploy serves new code before migrations are applied, driver-facing routes and any new schema-backed features can fail immediately with database errors.

## Recommended runtime layout

- Run Uvicorn behind a reverse proxy such as Nginx or Caddy.
- Terminate HTTPS at the proxy.
- Forward `X-Forwarded-Proto: https` to Django.
- Restrict `UVICORN_FORWARDED_ALLOW_IPS` to the reverse proxy addresses only.
- Expose `/healthz/` for web uptime checks. It verifies database and cache readiness and reports SMS worker state in the payload without failing the web probe.
- Expose `/healthz/worker/` for worker-specific monitoring. It returns a failure when the SMS worker heartbeat is missing or stale.
- Store secrets in the host platform secret manager, not in files committed to git.
- Back up PostgreSQL regularly.
- Example runtime files are included in `deploy/`:
  - `deploy/nginx-monettefarms.pre-tls.conf`
  - `deploy/nginx-monettefarms.conf`
  - `deploy/monettefarms-web.service`
  - `deploy/monettefarms-sms-worker.service`
  - `deploy/install-nginx-site.sh`
  - `deploy/server-preflight.sh`

## Operational notes

- Dispatcher routes require a staff account.
- The public driver form is open by design and rate limited by IP.
- SMS sends are queued in the database and must be processed by the `process_outbound_sms` worker.
- Start both the web service and the SMS worker service in production.
- The sample Nginx config assumes Let's Encrypt certificate paths for `your-domain.example`; replace them with your real domain before enabling the site.

## Nginx and Certbot flow

1. Before certificates exist, deploy `deploy/nginx-monettefarms.pre-tls.conf` as the active Nginx site.
2. Replace `your-domain.example` and `www.your-domain.example` with your real hostnames.
3. Reload Nginx and run Certbot:

```bash
sudo nginx -t
sudo systemctl reload nginx
sudo certbot --nginx -d your-domain.example -d www.your-domain.example
```

4. After certificates are issued, switch to `deploy/nginx-monettefarms.conf`, which contains the permanent HTTP-to-HTTPS redirect and explicit TLS server block.
5. Reload Nginx again and verify `https://your-domain.example/healthz/` and `https://your-domain.example/healthz/worker/`.

Helper commands:

```bash
./deploy/install-nginx-site.sh pre-tls your-domain.example www.your-domain.example
sudo certbot --nginx -d your-domain.example -d www.your-domain.example
./deploy/install-nginx-site.sh tls your-domain.example www.your-domain.example
./deploy/server-preflight.sh
```
