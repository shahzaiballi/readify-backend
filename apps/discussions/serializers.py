from django.utils import timezone
from rest_framework import serializers
from .models import Post, Reply, PostLike, ReplyLike


def format_time_ago(dt):
    """
    Converts a datetime to a human-readable "X time ago" string.
    Matches the timeAgo field your Flutter PostCard and ReplyCard display.
    """
    now = timezone.now()
    diff = now - dt

    seconds = int(diff.total_seconds())
    minutes = seconds // 60
    hours = minutes // 60
    days = hours // 24

    if seconds < 60:
        return 'Just now'
    elif minutes < 60:
        return f'{minutes} minute{"s" if minutes != 1 else ""} ago'
    elif hours < 24:
        return f'{hours} hour{"s" if hours != 1 else ""} ago'
    elif days < 7:
        return f'{days} day{"s" if days != 1 else ""} ago'
    else:
        weeks = days // 7
        return f'{weeks} week{"s" if weeks != 1 else ""} ago'


class ReplySerializer(serializers.ModelSerializer):
    """
    Matches your ReplyEntity exactly.
    Used in DiscussionDetailPage reply list.
    """
    userName = serializers.SerializerMethodField()
    userAvatarUrl = serializers.SerializerMethodField()
    timeAgo = serializers.SerializerMethodField()
    likesCount = serializers.IntegerField(source='likes_count')

    # Whether the requesting user has liked this reply
    isLikedByMe = serializers.SerializerMethodField()

    class Meta:
        model = Reply
        fields = [
            'id', 'userName', 'userAvatarUrl',
            'timeAgo', 'content', 'likesCount', 'isLikedByMe',
        ]

    def get_userName(self, obj):
        return obj.user.full_name or obj.user.email.split('@')[0]

    def get_userAvatarUrl(self, obj):
        if obj.user.avatar_url:
            return obj.user.avatar_url
        # Fallback to pravatar (matches your mock data pattern)
        return f'https://i.pravatar.cc/150?u={obj.user.email}'

    def get_timeAgo(self, obj):
        return format_time_ago(obj.created_at)

    def get_isLikedByMe(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return False
        return obj.reply_likes.filter(user=request.user).exists()


class PostListSerializer(serializers.ModelSerializer):
    """
    Used for the discussions feed list.
    Matches your PostEntity — contentSnippet is a truncated version.
    """
    userName = serializers.SerializerMethodField()
    userAvatarUrl = serializers.SerializerMethodField()
    timeAgo = serializers.SerializerMethodField()
    chapterTag = serializers.CharField(
        source='chapter_tag',
        allow_blank=True,
    )
    # Truncated content for feed cards — matches contentSnippet
    contentSnippet = serializers.SerializerMethodField()
    likesCount = serializers.IntegerField(source='likes_count')
    commentsCount = serializers.IntegerField(source='comments_count')
    bookId = serializers.SerializerMethodField()
    isLikedByMe = serializers.SerializerMethodField()

    class Meta:
        model = Post
        fields = [
            'id', 'userName', 'userAvatarUrl', 'timeAgo',
            'chapterTag', 'title', 'contentSnippet',
            'likesCount', 'commentsCount', 'bookId', 'isLikedByMe',
        ]

    def get_userName(self, obj):
        return obj.user.full_name or obj.user.email.split('@')[0]

    def get_userAvatarUrl(self, obj):
        if obj.user.avatar_url:
            return obj.user.avatar_url
        return f'https://i.pravatar.cc/150?u={obj.user.email}'

    def get_timeAgo(self, obj):
        return format_time_ago(obj.created_at)

    def get_contentSnippet(self, obj):
        # Truncate at 120 chars — matches your PostCard maxLines: 2 display
        if len(obj.content) > 120:
            return obj.content[:117] + '...'
        return obj.content

    def get_bookId(self, obj):
        return str(obj.book.id) if obj.book else ''

    def get_isLikedByMe(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return False
        return obj.post_likes.filter(user=request.user).exists()


class PostDetailSerializer(PostListSerializer):
    """
    Full post for DiscussionDetailPage.
    Extends list serializer — adds full content instead of snippet.
    """
    # Override snippet with full content for detail view
    contentSnippet = serializers.CharField(source='content')

    class Meta(PostListSerializer.Meta):
        fields = PostListSerializer.Meta.fields


class CreatePostSerializer(serializers.Serializer):
    """
    POST /discussions/
    Matches your NewDiscussionPage fields exactly.
    """
    title = serializers.CharField(max_length=255)
    content = serializers.CharField()
    book_id = serializers.UUIDField(required=False, allow_null=True)
    chapter_tag = serializers.CharField(
        max_length=50,
        required=False,
        allow_blank=True,
        default='',
    )

    def validate_book_id(self, value):
        if value is None:
            return value
        from apps.books.models import Book
        if not Book.objects.filter(id=value, is_published=True).exists():
            raise serializers.ValidationError('Book not found.')
        return value


class CreateReplySerializer(serializers.Serializer):
    """
    POST /discussions/{id}/replies/
    Matches your ReplyInputBar — just needs the content text.
    """
    content = serializers.CharField(min_length=1)