#!/usr/bin/env bash
set -e

# Apply any pending database migrations (runs on every deploy — safe + idempotent)
echo ">>> Running migrations..."
python manage.py migrate --noinput

# Collect static files
echo ">>> Collecting static files..."
python manage.py collectstatic --noinput --clear

# Create superuser automatically if env vars are set (Render free tier has no shell)
if [ -n "$SUPERUSER_EMAIL" ] && [ -n "$SUPERUSER_PASSWORD" ]; then
    python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(email='$SUPERUSER_EMAIL').exists():
    User.objects.create_superuser(email='$SUPERUSER_EMAIL', password='$SUPERUSER_PASSWORD', full_name='Admin')
    print('Superuser created: $SUPERUSER_EMAIL')
else:
    print('Superuser already exists')
"
fi

# Seed demo data if SEED_DEMO=true env var is set (Render free tier has no shell)
# WARNING: seed_demo wipes all data — remove this env var after first successful seed
if [ "$SEED_DEMO" = "true" ]; then
    echo ">>> SEED_DEMO=true detected — running seed_demo (this wipes existing data)..."
    python manage.py seed_demo
    echo ">>> Seed complete. Remove SEED_DEMO env var on Render to prevent re-seeding on next deploy."
fi

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
