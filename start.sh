#!/usr/bin/env bash
set -e

# Run Celery worker + beat combined in background
celery -A config worker \
    --beat \
    --loglevel=info \
    --concurrency=1 \
    --scheduler django_celery_beat.schedulers:DatabaseScheduler &

# Run Gunicorn as main process (keeps container alive)
exec gunicorn config.wsgi:application \
    --bind 0.0.0.0:$PORT \
    --workers 2 \
    --timeout 120
