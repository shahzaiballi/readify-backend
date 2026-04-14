from .base import *

DEBUG = True

# In development, use simpler email backend (prints to terminal)
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'