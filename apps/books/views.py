from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework import status

from .models import Book, Chapter, Chunk, Summary, Flashcard
from .serializers import (
    BookListSerializer, BookDetailSerializer,
    ChapterSerializer, ChunkSerializer,
    SummarySerializer, FlashcardSerializer,
)


class BookListView(APIView):
    """
    GET /books/
    Supports ?search=, ?category=, ?page=
    Used by your SearchPage and AllBooksPage.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        books = Book.objects.filter(is_published=True)

        # Search by title or author
        search = request.query_params.get('search')
        if search:
            books = books.filter(
                title__icontains=search
            ) | books.filter(
                author__icontains=search
            )

        # Filter by category
        category = request.query_params.get('category')
        if category:
            books = books.filter(category__iexact=category)

        serializer = BookListSerializer(
            books,
            many=True,
            context={'request': request}
        )
        return Response(serializer.data)


class RecommendedBooksView(APIView):
    """
    GET /books/recommended/
    Matches your recommendedBooksProvider.
    Returns is_recommended=True books.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        books = Book.objects.filter(
            is_published=True,
            is_recommended=True
        )
        serializer = BookListSerializer(
            books,
            many=True,
            context={'request': request}
        )
        return Response(serializer.data)


class TrendingBooksView(APIView):
    """
    GET /books/trending/
    Matches your trendingBooksProvider.
    Returns is_trending=True books with badge set.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        books = Book.objects.filter(
            is_published=True,
            is_trending=True
        ).order_by('badge')  # "#1" before "#2" etc.
        serializer = BookListSerializer(
            books,
            many=True,
            context={'request': request}
        )
        return Response(serializer.data)


class BookDetailView(APIView):
    """
    GET /books/{id}/
    Matches your BookDetailPage — full detail with user progress.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, book_id):
        try:
            book = Book.objects.get(id=book_id, is_published=True)
        except Book.DoesNotExist:
            return Response(
                {'error': 'Book not found.'},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = BookDetailSerializer(
            book,
            context={'request': request}
        )
        return Response(serializer.data)


class BookChaptersView(APIView):
    """
    GET /books/{id}/chapters/
    Matches your chapterListProvider and ChapterListPage.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, book_id):
        try:
            book = Book.objects.get(id=book_id, is_published=True)
        except Book.DoesNotExist:
            return Response(
                {'error': 'Book not found.'},
                status=status.HTTP_404_NOT_FOUND
            )

        chapters = book.chapters.all()
        serializer = ChapterSerializer(
            chapters,
            many=True,
            context={'request': request}
        )
        return Response(serializer.data)


class ChapterChunksView(APIView):
    """
    GET /chapters/{id}/chunks/
    Matches your getChunks() call in ChunkedReadingScreen.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, chapter_id):
        try:
            chapter = Chapter.objects.get(id=chapter_id)
        except Chapter.DoesNotExist:
            return Response(
                {'error': 'Chapter not found.'},
                status=status.HTTP_404_NOT_FOUND
            )

        chunks = chapter.chunks.all()
        serializer = ChunkSerializer(chunks, many=True)
        return Response(serializer.data)


class BookSummariesView(APIView):
    """
    GET /books/{id}/summaries/
    Matches your summaryControllerProvider and ChapterSummaryPage.
    Returns all chapter summaries for a book.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, book_id):
        try:
            book = Book.objects.get(id=book_id, is_published=True)
        except Book.DoesNotExist:
            return Response(
                {'error': 'Book not found.'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Get summaries through chapters
        summaries = Summary.objects.filter(
            chapter__book=book
        ).select_related('chapter').order_by('chapter__chapter_number')

        serializer = SummarySerializer(summaries, many=True)
        return Response(serializer.data)


class BookFlashcardsView(APIView):
    """
    GET /books/{id}/flashcards/
    Matches your flashcardsProvider and FlashcardPage.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, book_id):
        try:
            book = Book.objects.get(id=book_id, is_published=True)
        except Book.DoesNotExist:
            return Response(
                {'error': 'Book not found.'},
                status=status.HTTP_404_NOT_FOUND
            )

        flashcards = book.flashcards.all()
        serializer = FlashcardSerializer(flashcards, many=True)
        return Response(serializer.data)