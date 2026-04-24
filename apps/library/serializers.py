from rest_framework import serializers
from .models import UserBook, ChapterProgress
from apps.books.serializers import BookListSerializer


class LibraryBookSerializer(serializers.ModelSerializer):
    """
    Matches your LibraryBookEntity exactly.
    Combines UserBook fields with Book fields.
    """
    # All book fields flattened in (not nested)
    id = serializers.UUIDField(source='book.id')
    title = serializers.CharField(source='book.title')
    author = serializers.CharField(source='book.author')
    imageUrl = serializers.SerializerMethodField()  # Use method field like BookListSerializer
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

    class Meta:
        model = UserBook
        fields = [
            'id', 'title', 'author', 'imageUrl',
            'rating', 'readersCount', 'category',
            'hasAudio', 'badge',
            'progressPercent', 'isFavorite', 'status',
        ]

    def get_imageUrl(self, obj):
        """Get the cover image URL, supporting both uploaded files and URL strings."""
        request = self.context.get('request')
        url = obj.book.get_cover_url()
        # If it's a relative path from an uploaded file, make it absolute
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
    Matches actions from LibraryBookCard and CurrentlyReadingCard.
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
    Matches your UserProgressEntity used on the home screen
    in CurrentlyReadingCard.
    """
    bookId = serializers.UUIDField(source='book.id')
    title = serializers.CharField(source='book.title')
    author = serializers.CharField(source='book.author')
    imageUrl = serializers.SerializerMethodField()  # Use method field to handle all cases
    progressPercent = serializers.IntegerField(source='progress_percent')

    class Meta:
        model = UserBook
        fields = ['bookId', 'title', 'author', 'imageUrl', 'progressPercent']

    def get_imageUrl(self, obj):
        """Get the cover image URL, supporting both uploaded files and URL strings."""
        request = self.context.get('request')
        url = obj.book.get_cover_url()
        # If it's a relative path from an uploaded file, make it absolute
        if url and not url.startswith('http') and request:
            return request.build_absolute_uri(url)
        return url or ''