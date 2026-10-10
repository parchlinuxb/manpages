#!/usr/bin/env bash
# ==============================================================================
# Parch Man Pages - Container Entrypoint Script
# Runs inside the web container upon startup.
# ==============================================================================
set -e

echo "[entrypoint] Waiting for PostgreSQL database to be ready..."
until python -c "
import socket, sys
s = socket.socket()
s.settimeout(2)
try:
    s.connect(('db', 5432))
    sys.exit(0)
except Exception:
    sys.exit(1)
" 2>/dev/null; do
    sleep 1
done
echo "[entrypoint] Database connection established."

echo "[entrypoint] Running database migrations..."
python manage.py migrate --noinput

echo "[entrypoint] Starting Gunicorn web server..."
exec gunicorn wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers 4 \
    --threads 2 \
    --worker-class gthread \
    --timeout 120
