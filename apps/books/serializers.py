from rest_framework import serializers
from django.db.models import Sum
from .models import Book, Chapter, Chunk, Summary, Flashcard, UserUploadedBook, ReadingSchedule
from django.contrib.auth.models import AnonymousUser



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
    totalChapters = serializers.SerializerMethodField()
    pagesLeft = serializers.SerializerMethodField()
    flashcardsCount = serializers.SerializerMethodField()
    readPerDayMinutes = serializers.IntegerField(source='read_per_day_minutes')
    readPerDayPages = serializers.SerializerMethodField()
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
            'flashcardsCount', 'readPerDayMinutes', 'readPerDayPages',
        ]

    def get_readersCount(self, obj):
        return obj.formatted_readers_count()

    def get_imageUrl(self, obj):
        request = self.context.get('request')
        url = obj.get_cover_url()
        if url and not url.startswith('http') and request:
            return request.build_absolute_uri(url)
        return url or ''

    def get_totalChapters(self, obj):
        count = obj.chapters.count()
        return count if count > 0 else (obj.total_chapters or 0)

    def get_flashcardsCount(self, obj):
        try:
            return obj.flashcards.count()
        except Exception:
            return obj.flashcards_count or 0

    def get_progressPercent(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return 0
        user_book = obj.user_books.filter(user=request.user).first()
        return user_book.progress_percent if user_book else 0

    def get_pagesLeft(self, obj):
        from apps.books.models import Chunk
        request = self.context.get('request')
        user_book = obj.user_books.filter(user=request.user).first() if request else None
        progress = user_book.progress_percent if user_book else 0

        total_words = Chunk.objects.filter(chapter__book=obj).aggregate(
            total=Sum('words_count')
        )['total'] or 0

        if total_words == 0:
            total_words = obj.pages_left * 250 or 0

        remaining_words = int(total_words * (1 - progress / 100))
        return max(0, round(remaining_words / 250))

    def get_readPerDayPages(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return 10
        try:
            from apps.reading.models import ReadingPlan
            plan = request.user.reading_plan
            return plan.pages_per_day if plan else 10
        except Exception:
            return 10

    def get_daysLeftToFinish(self, obj):
        from apps.books.models import ReadingSchedule
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return 0
        try:
            schedule = ReadingSchedule.objects.get(user=request.user, book=obj)
            remaining = schedule.total_days - (schedule.current_day - 1)
            return max(0, remaining)
        except ReadingSchedule.DoesNotExist:
            pass
        user_book = obj.user_books.filter(user=request.user).first()
        if not user_book:
            return 0
        reading_plan = getattr(request.user, 'reading_plan', None)
        daily_minutes = reading_plan.daily_minutes if reading_plan else 30
        total_words = Chunk.objects.filter(chapter__book=obj).aggregate(
            total=Sum('words_count')
        )['total'] or 0
        words_remaining = int(total_words * (1 - user_book.progress_percent / 100))
        words_per_day = daily_minutes * 200
        if words_per_day <= 0:
            return 0
        return max(1, round(words_remaining / words_per_day))


class ChapterSerializer(serializers.ModelSerializer):
    """Matches ChapterEntity exactly."""
    chapterNumber = serializers.IntegerField(source='chapter_number')
    durationInMinutes = serializers.IntegerField(source='duration_in_minutes')
    pageRange = serializers.CharField(source='page_range')
    isLocked = serializers.BooleanField(source='is_locked')
    isCompleted = serializers.SerializerMethodField()
    isActive = serializers.SerializerMethodField()
    chapterSource = serializers.SerializerMethodField()

    class Meta:
        model = Chapter
        fields = [
            'id', 'title', 'chapterNumber',
            'durationInMinutes', 'pageRange',
            'isCompleted', 'isActive', 'isLocked', 'chapterSource',
        ]

    def get_chapterSource(self, obj):
        return obj.book.chapter_source

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
    dayNumber = serializers.IntegerField(source='day_number')
    wordsCount = serializers.IntegerField(source='words_count')

    class Meta:
        model = Chunk
        fields = ['id', 'text', 'estimatedMinutes', 'chunkIndex', 'dayNumber', 'wordsCount']


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
    """Flutter PDF upload serializer — includes reading preferences."""
    pdf_file = serializers.FileField()
    reading_mode = serializers.ChoiceField(
        choices=Book.ReadingMode.choices,
        default=Book.ReadingMode.DEEP,
        required=False,
    )
    daily_minutes = serializers.IntegerField(default=30, min_value=5, max_value=180, required=False)

    class Meta:
        model = UserUploadedBook
        fields = ['title', 'author', 'pdf_file', 'reading_mode', 'daily_minutes']
    
    def validate_pdf_file(self, value):
        """Validate PDF size/extension"""
        from django.conf import settings
        
        if not value.name.lower().endswith('.pdf'):
            raise serializers.ValidationError('Only PDF files supported')
        
        max_size = getattr(settings, 'PDF_MAX_UPLOAD_SIZE_MB', 50) * 1024 * 1024
        if value.size > max_size:
            raise serializers.ValidationError(f'Max size: {max_size//(1024*1024)}MB')
        
        return value
    
    def create(self, validated_data):
        request = self.context.get('request')

        if request and request.user and not isinstance(request.user, AnonymousUser):
            validated_data['uploaded_by'] = request.user
        else:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            system_user = User.objects.filter(is_superuser=True).first()
            if system_user:
                validated_data['uploaded_by'] = system_user
            else:
                raise serializers.ValidationError('No authenticated user available')

        upload = UserUploadedBook.objects.create(**validated_data)

        # Trigger Stage 1: Extract + Detect (not old process_user_uploaded_book)
        from apps.books.tasks import task_extract_and_detect
        import logging
        _log = logging.getLogger(__name__)
        try:
            task_extract_and_detect.delay(str(upload.id))
        except Exception as exc:
            _log.error(
                f'[Upload] Could not queue task for upload {upload.id}: {exc}. '
                f'Check CELERY_BROKER_URL env var and ensure Redis is reachable.',
                exc_info=True,
            )
            upload.status = UserUploadedBook.Status.FAILED
            upload.error_message = f'Celery broker unreachable — could not start processing: {exc}'
            upload.save(update_fields=['status', 'error_message'])

        return upload


class UserUploadStatusSerializer(serializers.ModelSerializer):
    """Flutter polls this for granular processing status."""
    bookId = serializers.SerializerMethodField()
    processingStatus = serializers.CharField(source='status')
    processingStage = serializers.CharField(source='processing_stage')
    totalPages = serializers.IntegerField(source='total_pages')
    detectedChapters = serializers.SerializerMethodField()

    class Meta:
        model = UserUploadedBook
        fields = [
            'id', 'title', 'processingStatus', 'processingStage',
            'bookId', 'error_message', 'totalPages', 'detectedChapters',
        ]

    def get_bookId(self, obj):
        return str(obj.book.id) if obj.book else None

    def get_detectedChapters(self, obj):
        """Return toc_raw chapter count when awaiting confirmation."""
        return len(obj.toc_raw) if obj.toc_raw else 0


class ReadingScheduleSerializer(serializers.ModelSerializer):
    """Serializes the reading schedule for GET /books/{id}/schedule/"""
    bookId = serializers.UUIDField(source='book.id', read_only=True)
    bookTitle = serializers.CharField(source='book.title', read_only=True)
    startDate = serializers.DateField(source='start_date')
    totalDays = serializers.IntegerField(source='total_days')
    scheduleData = serializers.JSONField(source='schedule_data')

    class Meta:
        model = ReadingSchedule
        fields = ['id', 'bookId', 'bookTitle', 'startDate', 'totalDays', 'scheduleData', 'created_at']