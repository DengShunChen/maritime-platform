#!/bin/sh
set -e
WORKERS="${GUNICORN_WORKERS:-1}"
exec gunicorn --log-file - --access-logfile - --log-level info \
  --workers "$WORKERS" --timeout 60 -b 0.0.0.0:5000 app_v2:app
