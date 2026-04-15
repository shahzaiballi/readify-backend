from rest_framework import serializers
from .models import Book, Chapter, Chunk, Summary, Flashcard


class BookListSerializer(serializers.ModelSerializer):
    """
    Used for list views: recommended, trending, library horizontal list.
    Matches your BookEntity fields exactly.
    """
    # Convert integer to "3M" string Flutter expects
    readersCount = serializers.SerializerMethodField()
    imageUrl = serializers.URLField(source='cover_image_url')
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


class BookDetailSerializer(serializers.ModelSerializer):
    """
    Used for BookDetailPage.
    Matches your BookDetailEntity — extends BookEntity fields.
    progressPercent and daysLeftToFinish are user-specific,
    computed from the requesting user's reading progress.
    """
    readersCount = serializers.SerializerMethodField()
    imageUrl = serializers.URLField(source='cover_image_url')
    hasAudio = serializers.BooleanField(source='has_audio')
    totalChapters = serializers.IntegerField(source='total_chapters')
    pagesLeft = serializers.IntegerField(source='pages_left')
    flashcardsCount = serializers.IntegerField(source='flashcards_count')
    readPerDayMinutes = serializers.IntegerField(source='read_per_day_minutes')

    # These are user-specific — injected by the view
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

    def get_progressPercent(self, obj):
        """
        Get this user's reading progress for this book.
        Returns 0 if the user hasn't started the book.
        """
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return 0
        user_book = obj.user_books.filter(user=request.user).first()
        return user_book.progress_percent if user_book else 0

    def get_daysLeftToFinish(self, obj):
        """
        Rough estimate: remaining pages / user's daily reading pace.
        """
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return 0
        user_book = obj.user_books.filter(user=request.user).first()
        if not user_book:
            return 0
        reading_plan = getattr(request.user, 'reading_plan', None)
        daily_minutes = reading_plan.daily_minutes if reading_plan else 45
        # Rough estimate: 1 page per minute
        pages_remaining = obj.pages_left * (1 - user_book.progress_percent / 100)
        if daily_minutes <= 0:
            return 0
        return max(1, round(pages_remaining / daily_minutes))


class ChapterSerializer(serializers.ModelSerializer):
    """
    Matches your ChapterEntity exactly.
    isCompleted and isActive are user-specific — injected by the view.
    """
    chapterNumber = serializers.IntegerField(source='chapter_number')
    durationInMinutes = serializers.IntegerField(source='duration_in_minutes')
    pageRange = serializers.CharField(source='page_range')
    isLocked = serializers.BooleanField(source='is_locked')

    # User-specific — computed in view context
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
        """True if user has finished all chunks in this chapter."""
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return False
        return obj.reading_progresses.filter(
            user_book__user=request.user,
            is_completed=True
        ).exists()

    def get_isActive(self, obj):
        """True if this is the chapter the user is currently reading."""
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return False
        return obj.reading_progresses.filter(
            user_book__user=request.user,
            is_active=True
        ).exists()


class ChunkSerializer(serializers.ModelSerializer):
    """Matches your ChunkEntity exactly — field names match Flutter camelCase."""
    chunkIndex = serializers.IntegerField(source='chunk_index')
    estimatedMinutes = serializers.IntegerField(source='estimated_minutes')

    class Meta:
        model = Chunk
        fields = ['id', 'text', 'estimatedMinutes', 'chunkIndex']


class SummarySerializer(serializers.ModelSerializer):
    """
    Matches your SummaryEntity.
    chapterNumber is derived from the related chapter.
    """
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
    """Matches your FlashcardEntity exactly."""
    bookId = serializers.UUIDField(source='book.id')

    class Meta:
        model = Flashcard
        fields = ['id', 'bookId', 'question', 'answer']