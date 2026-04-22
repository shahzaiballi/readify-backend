from django.urls import path
from . import views
from apps.library.views import CurrentProgressView

urlpatterns = [
    # Reading session — called when user advances a chunk
    path('session/', views.ReadingSessionView.as_view(), name='reading-session'),

    # Daily insights — home screen InsightsGrid
    path('insights/', views.InsightsView.as_view(), name='insights'),

    # Reading plan — ReadingPlanPage
    path('plan/', views.ReadingPlanView.as_view(), name='reading-plan'),

    # Current book progress — home screen CurrentlyReadingCard
    # Flutter calls GET /reading/progress/
    path('progress/', CurrentProgressView.as_view(), name='current-progress'),
]
