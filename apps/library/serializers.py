from rest_framework import serializers
from .models import UserBook, ChapterProgress
from apps.books.serializers import BookListSerializer


class LibraryBookSerializer(serializers.ModelSerializer):
    """
    Matches your LibraryBookEntity exactly.
    Combines UserBook fields with Book fields.
    """
    id = serializers.UUIDField(source='book.id')
    title = serializers.CharField(source='book.title')
    author = serializers.CharField(source='book.author')
    imageUrl = serializers.SerializerMethodField()
    rating = serializers.DecimalField(
        source='book.rating',
        max_digits=3,
        decimal_places=1
    )
    readersCount = serializers.SerializerMethodField()
    category = serializers.CharField(source='book.category')
    hasAudio = serializers.BooleanField(source='book.has_audio')
    badge = serializers.CharField(source='book.badge', allow_null=True)

    # Library-specific fields
    progressPercent = serializers.IntegerField(source='progress_percent')
    isFavorite = serializers.BooleanField(source='is_favorite')

    # Expose the UserBook's own id so Flutter can PATCH /library/{userBookId}/
    userBookId = serializers.UUIDField(source='id')

    class Meta:
        model = UserBook
        fields = [
            'id', 'userBookId', 'title', 'author', 'imageUrl',
            'rating', 'readersCount', 'category',
            'hasAudio', 'badge',
            'progressPercent', 'isFavorite', 'status',
        ]

    def get_imageUrl(self, obj):
        request = self.context.get('request')
        url = obj.book.get_cover_url()
        if url and not url.startswith('http') and request:
            return request.build_absolute_uri(url)
        return url or ''

    def get_readersCount(self, obj):
        return obj.book.formatted_readers_count()


class AddBookToLibrarySerializer(serializers.Serializer):
    """POST /library/ — add a book to the user's library"""
    book_id = serializers.UUIDField()

    def validate_book_id(self, value):
        from apps.books.models import Book
        if not Book.objects.filter(id=value, is_published=True).exists():
            raise serializers.ValidationError('Book not found.')
        return value


class UpdateLibraryBookSerializer(serializers.ModelSerializer):
    """
    PATCH /library/{id}/
    Update progress, status, or favorite.
    """
    progressPercent = serializers.IntegerField(
        source='progress_percent',
        min_value=0,
        max_value=100,
        required=False
    )
    isFavorite = serializers.BooleanField(source='is_favorite', required=False)

    class Meta:
        model = UserBook
        fields = ['progressPercent', 'isFavorite', 'status']


class UserProgressSerializer(serializers.ModelSerializer):
    """
    Matches your UserProgressEntity used on the home screen.
    Also returns currentChapterId so the app can resume reading at the
    correct chapter without hard-coding any value.
    """
    bookId = serializers.UUIDField(source='book.id')
    title = serializers.CharField(source='book.title')
    author = serializers.CharField(source='book.author')
    imageUrl = serializers.SerializerMethodField()
    progressPercent = serializers.IntegerField(source='progress_percent')

    # The chapter the user was last reading — null if they haven't started yet
    currentChapterId = serializers.SerializerMethodField()

    # The chunk index within that chapter
    currentChunkIndex = serializers.IntegerField(source='current_chunk_index')

    class Meta:
        model = UserBook
        fields = [
            'bookId', 'title', 'author', 'imageUrl',
            'progressPercent', 'currentChapterId', 'currentChunkIndex',
        ]

    def get_imageUrl(self, obj):
        request = self.context.get('request')
        url = obj.book.get_cover_url()
        if url and not url.startswith('http') and request:
            return request.build_absolute_uri(url)
        return url or ''

    def get_currentChapterId(self, obj):
        """
        Return the active chapter, falling back to the first chapter
        if the user hasn't started yet.
        """
        if obj.current_chapter_id:
            return str(obj.current_chapter_id)

        # Fall back to the first chapter of the book
        first_chapter = obj.book.chapters.order_by('chapter_number').first()
        if first_chapter:
            return str(first_chapter.id)
        return None