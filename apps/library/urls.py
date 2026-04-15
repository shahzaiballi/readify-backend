from django.urls import path
from . import views

urlpatterns = [
    path('', views.LibraryView.as_view(), name='library'),
    path('<uuid:pk>/', views.LibraryBookDetailView.as_view(), name='library-book-detail'),
]