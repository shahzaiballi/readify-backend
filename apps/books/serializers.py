"""
apps/books/serializers.py

Key changes from original:
- BookListSerializer.imageUrl now uses get_cover_url() (supports uploaded cover images)
- Added UserUploadSerializer for the user PDF upload endpoint
- Added UserUploadStatusSerializer so Flutter can poll processing status
"""

from rest_framework import serializers
from .models import Book, Chapter, Chunk, Summary, Flashcard, UserUploadedBook


class BookListSerializer(serializers.ModelSerializer):
    """
    Used for list views: recommended, trending, library horizontal list.
    Matches your BookEntity fields exactly.
    """
    readersCount = serializers.SerializerMethodField()
    # Use get_cover_url() so both uploaded files and URL strings work
    imageUrl = serializers.SerializerMethodField()
    hasAudio = serializers.BooleanField(source='has_audio')

    class Meta:
        model = Book
        fields = [
            'id', 'title', 'author', 'imageUrl',
            'rating', 'readersCount', 'category',
            'hasAudio', 'badge',
        ]

    def get_readersCount(self, obj):
        return obj.formatted_readers_count()

    def get_imageUrl(self, obj):
        request = self.context.get('request')
        url = obj.get_cover_url()
        # If it's a relative path from an uploaded file, make it absolute
        if url and not url.startswith('http') and request:
            return request.build_absolute_uri(url)
        return url or ''


class BookDetailSerializer(serializers.ModelSerializer):
    """
    Full detail for BookDetailPage.
    Matches BookDetailEntity — includes user-specific progress fields.
    """
    readersCount = serializers.SerializerMethodField()
    imageUrl = serializers.SerializerMethodField()
    hasAudio = serializers.BooleanField(source='has_audio')
    totalChapters = serializers.IntegerField(source='total_chapters')
    pagesLeft = serializers.IntegerField(source='pages_left')
    flashcardsCount = serializers.IntegerField(source='flashcards_count')
    readPerDayMinutes = serializers.IntegerField(source='read_per_day_minutes')
    progressPercent = serializers.SerializerMethodField()
    daysLeftToFinish = serializers.SerializerMethodField()

    class Meta:
        model = Book
        fields = [
            'id', 'title', 'author', 'imageUrl',
            'rating', 'readersCount', 'category',
            'hasAudio', 'badge', 'description',
            'totalChapters', 'progressPercent',
            'daysLeftToFinish', 'pagesLeft',
            'flashcardsCount', 'readPerDayMinutes',
        ]

    def get_readersCount(self, obj):
        return obj.formatted_readers_count()

    def get_imageUrl(self, obj):
        request = self.context.get('request')
        url = obj.get_cover_url()
        if url and not url.startswith('http') and request:
            return request.build_absolute_uri(url)
        return url or ''

    def get_progressPercent(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return 0
        user_book = obj.user_books.filter(user=request.user).first()
        return user_book.progress_percent if user_book else 0

    def get_daysLeftToFinish(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return 0
        user_book = obj.user_books.filter(user=request.user).first()
        if not user_book:
            return 0
        reading_plan = getattr(request.user, 'reading_plan', None)
        daily_minutes = reading_plan.daily_minutes if reading_plan else 45
        pages_remaining = obj.pages_left * (1 - user_book.progress_percent / 100)
        if daily_minutes <= 0:
            return 0
        return max(1, round(pages_remaining / daily_minutes))


class ChapterSerializer(serializers.ModelSerializer):
    """Matches ChapterEntity exactly."""
    chapterNumber = serializers.IntegerField(source='chapter_number')
    durationInMinutes = serializers.IntegerField(source='duration_in_minutes')
    pageRange = serializers.CharField(source='page_range')
    isLocked = serializers.BooleanField(source='is_locked')
    isCompleted = serializers.SerializerMethodField()
    isActive = serializers.SerializerMethodField()

    class Meta:
        model = Chapter
        fields = [
            'id', 'title', 'chapterNumber',
            'durationInMinutes', 'pageRange',
            'isCompleted', 'isActive', 'isLocked',
        ]

    def get_isCompleted(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return False
        return obj.reading_progresses.filter(
            user_book__user=request.user,
            is_completed=True
        ).exists()

    def get_isActive(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return False
        return obj.reading_progresses.filter(
            user_book__user=request.user,
            is_active=True
        ).exists()


class ChunkSerializer(serializers.ModelSerializer):
    """Matches ChunkEntity exactly."""
    chunkIndex = serializers.IntegerField(source='chunk_index')
    estimatedMinutes = serializers.IntegerField(source='estimated_minutes')

    class Meta:
        model = Chunk
        fields = ['id', 'text', 'estimatedMinutes', 'chunkIndex']


class SummarySerializer(serializers.ModelSerializer):
    """Matches SummaryEntity."""
    chapterNumber = serializers.IntegerField(source='chapter.chapter_number')
    summaryContent = serializers.CharField(source='summary_content')
    keyTakeaways = serializers.JSONField(source='key_takeaways')
    isLocked = serializers.BooleanField(source='is_locked')

    class Meta:
        model = Summary
        fields = [
            'id', 'chapterNumber', 'title',
            'summaryContent', 'keyTakeaways', 'isLocked',
        ]


class FlashcardSerializer(serializers.ModelSerializer):
    """Matches FlashcardEntity exactly."""
    bookId = serializers.UUIDField(source='book.id')

    class Meta:
        model = Flashcard
        fields = ['id', 'bookId', 'question', 'answer']


# ── User Upload Serializers ───────────────────────────────────────────────────

class UserUploadSerializer(serializers.ModelSerializer):
    """
    POST /books/upload/

    Accepts a PDF file + title + author from the Flutter AddBookPage.
    The actual processing happens in background via Celery.
    """
    class Meta:
        model = UserUploadedBook
        fields = ['id', 'title', 'author', 'pdf_file']
        extra_kwargs = {
            'pdf_file': {'required': True},
            'title': {'required': True},
        }

    def validate_pdf_file(self, value):
        """Validate file is a PDF and under size limit."""
        from django.conf import settings

        # Check file extension
        if not value.name.lower().endswith('.pdf'):
            raise serializers.ValidationError(
                'Only PDF files are supported. Please upload a .pdf file.'
            )

        # Check file size (convert MB to bytes)
        max_size_bytes = settings.PDF_MAX_UPLOAD_SIZE_MB * 1024 * 1024
        if value.size > max_size_bytes:
            raise serializers.ValidationError(
                f'PDF file is too large. Maximum size is {settings.PDF_MAX_UPLOAD_SIZE_MB}MB.'
            )

        return value


class UserUploadStatusSerializer(serializers.ModelSerializer):
    """
    GET /books/upload/<id>/status/

    Flutter polls this endpoint to check if processing is done.
    Returns the status and, when complete, the book_id so Flutter
    can navigate to the book detail page.
    """
    bookId = serializers.SerializerMethodField()
    processingStatus = serializers.CharField(source='status')

    class Meta:
        model = UserUploadedBook
        fields = ['id', 'title', 'processingStatus', 'bookId', 'error_message', 'uploaded_at']

    def get_bookId(self, obj):
        return str(obj.book.id) if obj.book else None