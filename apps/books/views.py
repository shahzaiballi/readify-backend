from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser
import logging

logger = logging.getLogger(__name__)

from .models import Book, Chapter, Chunk, Summary, Flashcard, UserUploadedBook
from .serializers import (
    BookListSerializer, BookDetailSerializer,
    ChapterSerializer, ChunkSerializer,
    SummarySerializer, FlashcardSerializer,
    UserUploadSerializer, UserUploadStatusSerializer,
)
from .tasks import process_user_uploaded_book


class BookListView(APIView):
    """
    GET /books/
    Supports ?search=, ?category=
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        books = Book.objects.filter(is_published=True)

        search = request.query_params.get('search')
        if search:
            books = books.filter(title__icontains=search) | books.filter(author__icontains=search)

        category = request.query_params.get('category')
        if category:
            books = books.filter(category__iexact=category)

        serializer = BookListSerializer(books, many=True, context={'request': request})
        return Response(serializer.data)


class RecommendedBooksView(APIView):
    """
    GET /books/recommended/
    Returns books marked is_recommended=True, EXCLUDING books the user
    already has in their library (so they don't see "read again" in recommended).
    Also excludes user-uploaded books (source='user_upload').
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Get IDs of books already in user's library
        user_book_ids = request.user.user_books.values_list('book_id', flat=True)

        books = Book.objects.filter(
            is_published=True,
            is_recommended=True,
            source=Book.Source.ADMIN,        # Only admin-curated books
        ).exclude(
            id__in=user_book_ids             # Exclude already-added books
        )

        serializer = BookListSerializer(books, many=True, context={'request': request})
        return Response(serializer.data)


class TrendingBooksView(APIView):
    """GET /books/trending/"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        books = Book.objects.filter(
            is_published=True,
            is_trending=True,
            source=Book.Source.ADMIN,
        ).order_by('badge')
        serializer = BookListSerializer(books, many=True, context={'request': request})
        return Response(serializer.data)


class BookDetailView(APIView):
    """GET /books/{id}/"""
    permission_classes = [IsAuthenticated]

    def get(self, request, book_id):
        try:
            book = Book.objects.get(id=book_id, is_published=True)
        except Book.DoesNotExist:
            return Response({'error': 'Book not found.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = BookDetailSerializer(book, context={'request': request})
        return Response(serializer.data)


class BookChaptersView(APIView):
    """GET /books/{id}/chapters/"""
    permission_classes = [IsAuthenticated]

    def get(self, request, book_id):
        try:
            book = Book.objects.get(id=book_id, is_published=True)
        except Book.DoesNotExist:
            return Response({'error': 'Book not found.'}, status=status.HTTP_404_NOT_FOUND)

        chapters = book.chapters.all()
        serializer = ChapterSerializer(chapters, many=True, context={'request': request})
        return Response(serializer.data)


class ChapterChunksView(APIView):
    """GET /books/chapters/{id}/chunks/"""
    permission_classes = [IsAuthenticated]

    def get(self, request, chapter_id):
        try:
            chapter = Chapter.objects.get(id=chapter_id)
        except Chapter.DoesNotExist:
            return Response({'error': 'Chapter not found.'}, status=status.HTTP_404_NOT_FOUND)

        chunks = chapter.chunks.all()
        serializer = ChunkSerializer(chunks, many=True)
        return Response(serializer.data)


class BookSummariesView(APIView):
    """GET /books/{id}/summaries/"""
    permission_classes = [IsAuthenticated]

    def get(self, request, book_id):
        try:
            book = Book.objects.get(id=book_id, is_published=True)
        except Book.DoesNotExist:
            return Response({'error': 'Book not found.'}, status=status.HTTP_404_NOT_FOUND)

        summaries = Summary.objects.filter(
            chapter__book=book
        ).select_related('chapter').order_by('chapter__chapter_number')

        serializer = SummarySerializer(summaries, many=True)
        return Response(serializer.data)


class BookFlashcardsView(APIView):
    """GET /books/{id}/flashcards/"""
    permission_classes = [IsAuthenticated]

    def get(self, request, book_id):
        try:
            book = Book.objects.get(id=book_id, is_published=True)
        except Book.DoesNotExist:
            return Response({'error': 'Book not found.'}, status=status.HTTP_404_NOT_FOUND)

        flashcards = book.flashcards.all()
        serializer = FlashcardSerializer(flashcards, many=True)
        return Response(serializer.data)


# ── User Upload Views ─────────────────────────────────────────────────────────
class UserBookUploadView(APIView):
    """✅ FIXED: PDF upload from Flutter - passes request context"""
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [IsAuthenticated]  # ✅ CHANGED: Now requires auth

    def post(self, request):
        logger.info(f"📤 UPLOAD HIT! User: {request.user}, Files: {request.FILES}, Data: {request.data}")
        
        # ✅ Pass request context to serializer so it can access user
        serializer = UserUploadSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            upload = serializer.save()  # ✅ Now properly sets uploaded_by
            
            # Queue Celery processing
            process_user_uploaded_book.delay(str(upload.id))
            
            logger.info(f"✅ Upload created ID: {upload.id} by user: {request.user}")
            return Response({
                'message': '✅ Upload accepted - processing...',
                'id': str(upload.id),
                'upload_url': request.build_absolute_uri(upload.pdf_file.url)
            }, status=status.HTTP_202_ACCEPTED)
        
        logger.error(f"❌ Upload errors: {serializer.errors}")
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UserUploadStatusView(APIView):
    """GET /books/upload/<id>/status/ - Flutter polls this"""
    permission_classes = [AllowAny]

    def get(self, request, upload_id):
        try:
            upload = UserUploadedBook.objects.get(id=upload_id)
        except UserUploadedBook.DoesNotExist:
            return Response({'error': 'Upload not found'}, status=status.HTTP_404_NOT_FOUND)

        serializer = UserUploadStatusSerializer(upload)
        return Response(serializer.data)