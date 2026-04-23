from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/auth/', include('apps.users.urls')),
    path('api/v1/books/', include('apps.books.urls')),
    path('api/v1/library/', include('apps.library.urls')),
    path('api/v1/reading/', include('apps.reading.urls')),
    path('api/v1/discussions/', include('apps.discussions.urls')),
]

# Serve uploaded media files in development
# In production, nginx/S3 handles this instead
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)