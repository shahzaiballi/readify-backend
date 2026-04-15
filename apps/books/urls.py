from django.urls import path
from . import views

urlpatterns = [
    # Book lists
    path('', views.BookListView.as_view(), name='book-list'),
    path('recommended/', views.RecommendedBooksView.as_view(), name='recommended-books'),
    path('trending/', views.TrendingBooksView.as_view(), name='trending-books'),

    # Book detail + related content
    path('<uuid:book_id>/', views.BookDetailView.as_view(), name='book-detail'),
    path('<uuid:book_id>/chapters/', views.BookChaptersView.as_view(), name='book-chapters'),
    path('<uuid:book_id>/summaries/', views.BookSummariesView.as_view(), name='book-summaries'),
    path('<uuid:book_id>/flashcards/', views.BookFlashcardsView.as_view(), name='book-flashcards'),

    # Chunks live under chapter ID (matches your /read/:bookId/:chapterId route)
    path('chapters/<uuid:chapter_id>/chunks/', views.ChapterChunksView.as_view(), name='chapter-chunks'),
]