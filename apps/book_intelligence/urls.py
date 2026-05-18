from django.urls import path
from . import views

app_name = 'book_intelligence'

urlpatterns = [
    # Pipeline trigger & status
    path('books/<uuid:book_id>/analyze/', views.AnalyzeBookView.as_view(), name='analyze-book'),
    path('books/<uuid:book_id>/status/', views.IntelligenceStatusView.as_view(), name='intelligence-status'),

    # Book Brief
    path('books/<uuid:book_id>/brief/', views.BookBriefView.as_view(), name='book-brief'),

    # AI Chapter structure
    path('books/<uuid:book_id>/chapters/', views.AIChaptersView.as_view(), name='ai-chapters'),
    path('books/<uuid:book_id>/chapters/confirm/', views.ConfirmChaptersView.as_view(), name='confirm-chapters'),
    path('books/<uuid:book_id>/chapters/<uuid:chapter_id>/', views.AIChapterDetailView.as_view(), name='ai-chapter-detail'),

    # Chapter summary by reading mode
    path(
        'books/<uuid:book_id>/chapters/<uuid:chapter_id>/summary/',
        views.ChapterSummaryByModeView.as_view(),
        name='chapter-summary-mode',
    ),

    # Ask Your Book (Q&A)
    path('books/<uuid:book_id>/qa/', views.AskYourBookView.as_view(), name='ask-book'),
    path('books/<uuid:book_id>/qa/history/', views.QAHistoryView.as_view(), name='qa-history'),

    # Smart Notifications
    path('books/<uuid:book_id>/notifications/today/', views.TodayNotificationsView.as_view(), name='today-notifications'),
    path('books/<uuid:book_id>/notifications/generate/', views.GenerateNotificationsView.as_view(), name='generate-notifications'),
]
