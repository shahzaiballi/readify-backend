from django.urls import path
from . import views

urlpatterns = [
    # Full library list + add book to library
    path('', views.LibraryView.as_view(), name='library'),

    # Update or delete a specific book in the library
    path('<uuid:pk>/', views.LibraryBookDetailView.as_view(), name='library-book-detail'),
]
