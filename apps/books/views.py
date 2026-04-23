"""
apps/books/views.py

Key additions:
- RecommendedBooksView: excludes books the user already has in their library
- UserBookUploadView: accepts PDF upload from Flutter, triggers background processing
- UserUploadStatusView: Flutter polls this to check processing progress
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser

from .models import Book, Chapter, Chunk, Summary, Flashcard, UserUploadedBook
from .serializers import (
    BookListSerializer, BookDetailSerializer,
    ChapterSerializer, ChunkSerializer,
    SummarySerializer, FlashcardSerializer,
    UserUploadSerializer, UserUploadStatusSerializer,
)


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
    """
    POST /books/upload/

    Called from Flutter's AddBookPage when user selects a PDF.
    Accepts multipart/form-data with:
        - pdf_file: the PDF binary
        - title: book title (required)
        - author: book author (optional)

    Returns immediately with upload_id.
    Flutter should then poll GET /books/upload/<id>/status/ to check progress.

    Example Flutter usage:
        final request = http.MultipartRequest('POST', uri);
        request.fields['title'] = titleController.text;
        request.fields['author'] = authorController.text;
        request.files.add(await http.MultipartFile.fromPath('pdf_file', filePath));
    """
    permission_classes = [IsAuthenticated]
    # MultiPartParser handles file uploads; FormParser handles form fields
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        serializer = UserUploadSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # Create the upload record, linking it to the current user
        upload = serializer.save(uploaded_by=request.user)

        # Trigger background processing
        from .tasks import process_user_uploaded_book
        process_user_uploaded_book.delay(str(upload.id))

        return Response({
            'uploadId': str(upload.id),
            'title': upload.title,
            'status': upload.status,
            'message': (
                'Upload received. Your book is being processed. '
                'It will appear in your library in 1-2 minutes.'
            ),
        }, status=status.HTTP_202_ACCEPTED)


class UserUploadStatusView(APIView):
    """
    GET /books/upload/<upload_id>/status/

    Flutter polls this endpoint every few seconds after uploading a PDF.
    When processingStatus == 'completed', Flutter can navigate to the book.

    Response:
        {
          "id": "...",
          "title": "My Book",
          "processingStatus": "processing",  // pending|processing|completed|failed
          "bookId": null,                    // filled when completed
          "error_message": ""
        }
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, upload_id):
        try:
            # Users can only check their own uploads
            upload = UserUploadedBook.objects.get(
                id=upload_id,
                uploaded_by=request.user,
            )
        except UserUploadedBook.DoesNotExist:
            return Response({'error': 'Upload not found.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = UserUploadStatusSerializer(upload)
        return Response(serializer.data)