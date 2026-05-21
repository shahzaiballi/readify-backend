from .base import *

DEBUG = False

ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='').split(',')

# ── Cloudinary app (must be in INSTALLED_APPS so SDK gets configured) ─────────
INSTALLED_APPS += ['cloudinary_storage', 'cloudinary']

# ── Whitenoise (static files — no nginx needed) ───────────────────────────────
MIDDLEWARE.insert(1, 'whitenoise.middleware.WhiteNoiseMiddleware')

# ── Storage backends (Django 4.2+ format) ─────────────────────────────────────
STORAGES = {
    'default': {
        'BACKEND': 'cloudinary_storage.storage.MediaCloudinaryStorage',
    },
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
    },
}

# ── Cloudinary credentials ─────────────────────────────────────────────────────
CLOUDINARY_STORAGE = {
    'CLOUD_NAME': config('CLOUDINARY_CLOUD_NAME', default=''),
    'API_KEY': config('CLOUDINARY_API_KEY', default=''),
    'API_SECRET': config('CLOUDINARY_API_SECRET', default=''),
}

# ── CORS (restrict to Flutter app in production) ──────────────────────────────
CORS_ALLOW_ALL_ORIGINS = True  # Fine for mobile APK distribution

# ── Security headers ─────────────────────────────────────────────────────────
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_SSL_REDIRECT = False  # Railway handles SSL termination at load balancer
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True