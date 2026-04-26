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
    already has in their library.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user_book_ids = request.user.user_books.values_list('book_id', flat=True)

        books = Book.objects.filter(
            is_published=True,
            is_recommended=True,
            source=Book.Source.ADMIN,
        ).exclude(
            id__in=user_book_ids
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
    """
    GET /books/{book_id}/chapters/{chapter_id}/chunks/
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, book_id, chapter_id):
        try:
            chapter = Chapter.objects.get(id=chapter_id, book_id=book_id)
        except Chapter.DoesNotExist:
            return Response(
                {'error': 'Chapter not found for this book.'},
                status=status.HTTP_404_NOT_FOUND,
            )

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
    """
    POST /books/upload/

    Accepts PDF uploads from users and queues background AI processing.
    
    Changes vs original:
    - Cover image is extracted from the first page of the PDF by the Celery task
      (more reliable than external APIs). This ensures all user uploads get a
      visual representation, even if external cover services are unavailable.
    - Book is immediately visible in the library, but processing happens in background.
    """
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        logger.info(
            f"📤 UPLOAD HIT! User: {request.user}, "
            f"Files: {list(request.FILES.keys())}, "
            f"Data: {dict(request.data)}"
        )

        serializer = UserUploadSerializer(data=request.data, context={'request': request})

        if not serializer.is_valid():
            logger.error(f"❌ Upload validation errors: {serializer.errors}")
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        title = serializer.validated_data['title']
        author = serializer.validated_data.get('author', '')

        # ── Step 1: Create the Book placeholder (no cover yet) ─────────────────
        # We skip external cover fetching here and let the Celery task handle it.
        # This way, user uploads get the actual PDF first page as cover
        # (which is more reliable than external APIs).
        book = Book.objects.create(
            title=title,
            author=author or 'Unknown Author',
            category='User Upload',
            source=Book.Source.USER_UPLOAD,
            processing_status=Book.ProcessingStatus.PENDING,
            is_published=True,
            is_recommended=False,
            is_trending=False,
            description=f'Uploaded by {request.user.email}',
            # No cover set here — Celery task will extract from PDF
        )
        logger.info(f"📚 Created placeholder Book: {book.id} — '{book.title}'")

        # ── Step 2: Create the UserUploadedBook record ────────────────────────
        upload = UserUploadedBook.objects.create(
            uploaded_by=request.user,
            title=title,
            author=author,
            pdf_file=serializer.validated_data['pdf_file'],
            book=book,
            status=UserUploadedBook.Status.PENDING,
        )
        logger.info(f"📄 Created UserUploadedBook: {upload.id}, book={book.id}")

        # ── Step 3: Add book to user's library immediately ────────────────────
        from apps.library.models import UserBook
        user_book, created = UserBook.objects.get_or_create(
            user=request.user,
            book=book,
            defaults={'status': UserBook.Status.NOT_STARTED},
        )
        logger.info(
            f"📖 UserBook {'created' if created else 'already existed'}: "
            f"user={request.user.email}, book={book.id}"
        )

        # ── Step 4: Queue background PDF processing ───────────────────────────
        process_user_uploaded_book.delay(str(upload.id))
        logger.info(f"⚙️  Celery task queued for upload {upload.id}")

        return Response(
            {
                'message': '✅ Upload accepted — Cover will be extracted from PDF during processing.',
                'id': str(upload.id),
                'book_id': str(book.id),
            },
            status=status.HTTP_202_ACCEPTED,
        )


class UserUploadStatusView(APIView):
    """GET /books/upload/<id>/status/ — Flutter polls this"""
    permission_classes = [AllowAny]

    def get(self, request, upload_id):
        try:
            upload = UserUploadedBook.objects.get(id=upload_id)
        except UserUploadedBook.DoesNotExist:
            return Response({'error': 'Upload not found'}, status=status.HTTP_404_NOT_FOUND)

        serializer = UserUploadStatusSerializer(upload)
        return Response(serializer.data)