from django.urls import path
from . import views

urlpatterns = [
    path('session/', views.ReadingSessionView.as_view(), name='reading-session'),
    path('insights/', views.InsightsView.as_view(), name='insights'),
    path('plan/', views.ReadingPlanView.as_view(), name='reading-plan'),
]