from rest_framework import serializers
from .models import Book, Chapter, Chunk, Summary, Flashcard, UserUploadedBook
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
    """✅ FIXED: Flutter PDF upload serializer - properly handles uploaded_by"""
    pdf_file = serializers.FileField()

    class Meta:
        model = UserUploadedBook
        fields = ['title', 'author', 'pdf_file']
    
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
        """✅ FIXED: Properly set uploaded_by from request.user"""
        request = self.context.get('request')
        
        # Get authenticated user or create a default system user
        if request and request.user and not isinstance(request.user, AnonymousUser):
            validated_data['uploaded_by'] = request.user
        else:
            # Fallback: get first superuser or create a system user
            from django.contrib.auth import get_user_model
            User = get_user_model()
            system_user = User.objects.filter(is_superuser=True).first()
            if system_user:
                validated_data['uploaded_by'] = system_user
            else:
                raise serializers.ValidationError("No authenticated user available")
        
        return UserUploadedBook.objects.create(**validated_data)


class UserUploadStatusSerializer(serializers.ModelSerializer):
    """Flutter polls this for processing status"""
    bookId = serializers.SerializerMethodField()
    processingStatus = serializers.CharField(source='status')

    class Meta:
        model = UserUploadedBook
        fields = ['id', 'title', 'processingStatus', 'bookId', 'error_message']

    def get_bookId(self, obj):
        return str(obj.book.id) if obj.book else None