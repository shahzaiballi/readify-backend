from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/auth/', include('apps.users.urls')),
    path('api/v1/books/', include('apps.books.urls')),
    path('api/v1/library/', include('apps.library.urls')),
    path('api/v1/reading/', include('apps.reading.urls')),
]