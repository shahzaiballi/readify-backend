from django.urls import path
from . import views

urlpatterns = [
    # ── Book Lists ────────────────────────────────────────────────────────────
    path('', views.BookListView.as_view(), name='book-list'),
    path('recommended/', views.RecommendedBooksView.as_view(), name='recommended-books'),
    path('trending/', views.TrendingBooksView.as_view(), name='trending-books'),

    # ── User PDF Upload ───────────────────────────────────────────────────────
    # POST: upload a PDF book (triggers background AI processing)
    path('upload/', views.UserBookUploadView.as_view(), name='user-book-upload'),
    # GET: poll processing status after upload
    path('upload/<uuid:upload_id>/status/', views.UserUploadStatusView.as_view(), name='upload-status'),

    # ── Book Detail & Related Content ─────────────────────────────────────────
    path('<uuid:book_id>/', views.BookDetailView.as_view(), name='book-detail'),
    path('<uuid:book_id>/chapters/', views.BookChaptersView.as_view(), name='book-chapters'),
    path('<uuid:book_id>/summaries/', views.BookSummariesView.as_view(), name='book-summaries'),
    path('<uuid:book_id>/flashcards/', views.BookFlashcardsView.as_view(), name='book-flashcards'),

    # ── Chunks (nested under book + chapter for RESTful consistency) ──────────
    # Flutter calls: GET /api/v1/books/{book_id}/chapters/{chapter_id}/chunks/
    path(
        '<uuid:book_id>/chapters/<uuid:chapter_id>/chunks/',
        views.ChapterChunksView.as_view(),
        name='chapter-chunks',
    ),
]