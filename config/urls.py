# pyrefly: ignore [missing-import]
from django.contrib import admin
# pyrefly: ignore [missing-import]
from django.urls import path, include
# pyrefly: ignore [missing-import]
from django.conf import settings
# pyrefly: ignore [missing-import]
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/auth/', include('apps.users.urls')),
    path('api/v1/users/', include('apps.users.urls')),
    path('api/v1/books/', include('apps.books.urls')),
    path('api/v1/library/', include('apps.library.urls')),
    path('api/v1/reading/', include('apps.reading.urls')),
    path('api/v1/community/', include('apps.community.urls')),
    path('api/v1/intelligence/', include('apps.book_intelligence.urls')),
    # Discussions removed — replaced by Community
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)