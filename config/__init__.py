"""
config/__init__.py

Import Celery app so it is loaded when Django starts.
This ensures tasks are registered properly.
"""

from .celery import app as celery_app

__all__ = ('celery_app',)