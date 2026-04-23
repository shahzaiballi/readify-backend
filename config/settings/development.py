from .base import *

DEBUG = True

# In development, print emails to terminal instead of sending them
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Allow all origins in dev
CORS_ALLOW_ALL_ORIGINS = True