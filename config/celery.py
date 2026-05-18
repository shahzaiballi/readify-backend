"""
config/celery.py

Celery application setup for Readify background tasks.

HOW TO RUN (in a separate terminal while Django is running):
    celery -A config worker --loglevel=info

This starts the background worker that processes PDF chunking tasks.
"""

import os
from celery import Celery
from celery.schedules import crontab

# Tell Celery which Django settings file to use
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')

app = Celery('readify')

# Load config from Django settings — all Celery settings start with CELERY_
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks in all INSTALLED_APPS
# Celery will look for a tasks.py file in each app
app.autodiscover_tasks()

# ── Celery Beat Schedules ─────────────────────────────────────────────────────
app.conf.beat_schedule = {
    'readify_nightly_notifications': {
        'task': 'book_intelligence.dispatch_nightly_notifications',
        'schedule': crontab(hour=23, minute=0),  # Every night at 11:00 PM UTC
    },
}
app.conf.timezone = 'UTC'


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f'Request: {self.request!r}')