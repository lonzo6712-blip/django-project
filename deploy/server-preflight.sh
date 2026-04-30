#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${APP_ROOT:-/srv/monettefarms}"
APP_DIR="${APP_DIR:-$APP_ROOT/app}"
ENV_FILE="${ENV_FILE:-$APP_ROOT/.env}"
LOCAL_HEALTH_URL="${LOCAL_HEALTH_URL:-http://127.0.0.1:8000/healthz/}"
LOCAL_WORKER_HEALTH_URL="${LOCAL_WORKER_HEALTH_URL:-http://127.0.0.1:8000/healthz/worker/}"

required_env_vars=(
  DJANGO_ENV
  DJANGO_SECRET_KEY
  DJANGO_ALLOWED_HOSTS
  DJANGO_CSRF_TRUSTED_ORIGINS
  DATABASE_URL
  CACHE_URL
  SMS_BACKEND
  UVICORN_FORWARDED_ALLOW_IPS
)

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

require_command systemctl
require_command curl
require_command python3

echo "Checking app directory..."
test -d "$APP_DIR"

echo "Checking env file..."
test -f "$ENV_FILE"

for var_name in "${required_env_vars[@]}"; do
  if ! grep -q "^${var_name}=" "$ENV_FILE"; then
    echo "Missing required env var in $ENV_FILE: $var_name" >&2
    exit 1
  fi
done

echo "Checking Python environment..."
test -x "$APP_DIR/.venv/bin/python"

echo "Checking services..."
systemctl is-active --quiet postgresql
systemctl is-active --quiet redis-server
systemctl is-active --quiet nginx
systemctl is-active --quiet monettefarms-web
systemctl is-active --quiet monettefarms-sms-worker

echo "Checking Redis..."
require_command redis-cli
redis-cli ping | grep -q '^PONG$'

echo "Checking Django health endpoint..."
health_output="$(curl --silent --show-error --fail "$LOCAL_HEALTH_URL")"
echo "$health_output"

python3 - "$health_output" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
expected = {
    "status": "ok",
    "database": "ok",
    "cache": "ok",
}
for key, expected_value in expected.items():
    actual = payload.get(key)
    if actual != expected_value:
        raise SystemExit(f"Health check failed for {key}: expected {expected_value!r}, got {actual!r}")
PY

echo "Checking SMS worker health endpoint..."
worker_health_output="$(curl --silent --show-error --fail "$LOCAL_WORKER_HEALTH_URL")"
echo "$worker_health_output"

python3 - "$worker_health_output" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
expected = {
    "status": "ok",
    "sms_worker": "ok",
}
for key, expected_value in expected.items():
    actual = payload.get(key)
    if actual != expected_value:
        raise SystemExit(f"Worker health check failed for {key}: expected {expected_value!r}, got {actual!r}")
PY

echo "Preflight passed."
