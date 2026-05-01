"""
apps/community/serializers.py
"""

from rest_framework import serializers
from .models import Community, CommunityMember, Message, MessageReaction
from django.utils import timezone


class MemberUserSerializer(serializers.Serializer):
    """Lightweight user info shown in member list."""
    id = serializers.UUIDField()
    name = serializers.SerializerMethodField()
    avatarUrl = serializers.SerializerMethodField()
    memberSince = serializers.SerializerMethodField()
    booksReading = serializers.SerializerMethodField()

    def get_name(self, obj):
        return obj.user.full_name or obj.user.email.split('@')[0]

    def get_avatarUrl(self, obj):
        request = self.context.get('request')
        if obj.user.avatar:
            if request:
                return request.build_absolute_uri(obj.user.avatar.url)
            return obj.user.avatar.url
        return f'https://i.pravatar.cc/150?u={obj.user.email}'

    def get_memberSince(self, obj):
        return obj.joined_at.strftime('%b %Y')

    def get_booksReading(self, obj):
        return obj.user.user_books.filter(
            status__in=['in_progress', 'not_started']
        ).count()

    class Meta:
        model = CommunityMember
        fields = ['id', 'name', 'avatarUrl', 'memberSince', 'booksReading']


class ReactionSummarySerializer(serializers.Serializer):
    emoji = serializers.CharField()
    count = serializers.IntegerField()
    reactedByMe = serializers.BooleanField()


class ReplyPreviewSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    senderName = serializers.SerializerMethodField()
    contentPreview = serializers.SerializerMethodField()

    def get_senderName(self, obj):
        return obj.sender.full_name or obj.sender.email.split('@')[0]

    def get_contentPreview(self, obj):
        return obj.content[:60] + '...' if len(obj.content) > 60 else obj.content


class MessageSerializer(serializers.ModelSerializer):
    senderId = serializers.UUIDField(source='sender.id')
    senderName = serializers.SerializerMethodField()
    senderAvatarUrl = serializers.SerializerMethodField()
    reactions = serializers.SerializerMethodField()
    replyTo = serializers.SerializerMethodField()
    isDeleted = serializers.BooleanField(source='is_deleted')
    isMine = serializers.SerializerMethodField()
    timeLabel = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = [
            'id', 'senderId', 'senderName', 'senderAvatarUrl',
            'content', 'reactions', 'replyTo',
            'isDeleted', 'isMine', 'timeLabel', 'created_at',
        ]

    def get_senderName(self, obj):
        return obj.sender.full_name or obj.sender.email.split('@')[0]

    def get_senderAvatarUrl(self, obj):
        request = self.context.get('request')
        if obj.sender.avatar:
            if request:
                return request.build_absolute_uri(obj.sender.avatar.url)
            return obj.sender.avatar.url
        return f'https://i.pravatar.cc/150?u={obj.sender.email}'

    def get_reactions(self, obj):
        request = self.context.get('request')
        user = request.user if request else None
        raw = obj.reactions.values('emoji').annotate(
            count=serializers.IntegerField.__class__  # placeholder
        )
        # Manual aggregation
        emoji_map = {}
        for r in obj.reactions.all():
            if r.emoji not in emoji_map:
                emoji_map[r.emoji] = {'count': 0, 'reactedByMe': False}
            emoji_map[r.emoji]['count'] += 1
            if user and r.user_id == user.id:
                emoji_map[r.emoji]['reactedByMe'] = True
        return [
            {'emoji': e, 'count': v['count'], 'reactedByMe': v['reactedByMe']}
            for e, v in emoji_map.items()
        ]

    def get_replyTo(self, obj):
        if obj.reply_to and not obj.reply_to.is_deleted:
            return {
                'id': str(obj.reply_to.id),
                'senderName': obj.reply_to.sender.full_name or obj.reply_to.sender.email.split('@')[0],
                'contentPreview': obj.reply_to.content[:60],
            }
        return None

    def get_isMine(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return False
        return obj.sender_id == request.user.id

    def get_timeLabel(self, obj):
        now = timezone.now()
        diff = now - obj.created_at
        minutes = int(diff.total_seconds() // 60)
        hours = minutes // 60
        days = hours // 24
        if minutes < 1:
            return 'now'
        if minutes < 60:
            return f'{minutes}m'
        if hours < 24:
            return f'{hours}h'
        if days < 7:
            return f'{days}d'
        return obj.created_at.strftime('%d %b')


class CommunityListSerializer(serializers.ModelSerializer):
    isMember = serializers.SerializerMethodField()
    isAdmin = serializers.SerializerMethodField()
    bookTitle = serializers.SerializerMethodField()
    bookCover = serializers.SerializerMethodField()
    lastMessage = serializers.SerializerMethodField()
    coverImageUrl = serializers.SerializerMethodField()

    class Meta:
        model = Community
        fields = [
            'id', 'name', 'description', 'community_type',
            'privacy', 'member_count', 'cover_emoji',
            'coverImageUrl', 'bookTitle', 'bookCover',
            'isMember', 'isAdmin', 'lastMessage', 'created_at',
        ]

    def get_isMember(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return False
        return obj.members.filter(user=request.user).exists()

    def get_isAdmin(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return False
        return obj.members.filter(user=request.user, role='admin').exists()

    def get_bookTitle(self, obj):
        return obj.book.title if obj.book else None

    def get_bookCover(self, obj):
        if not obj.book:
            return None
        request = self.context.get('request')
        url = obj.book.get_cover_url()
        if url and not url.startswith('http') and request:
            return request.build_absolute_uri(url)
        return url or None

    def get_lastMessage(self, obj):
        msg = obj.messages.filter(is_deleted=False).last()
        if not msg:
            return None
        return {
            'senderName': msg.sender.full_name or msg.sender.email.split('@')[0],
            'content': msg.content[:60],
            'timeLabel': MessageSerializer(msg, context=self.context).get_timeLabel(msg),
        }

    def get_coverImageUrl(self, obj):
        request = self.context.get('request')
        if obj.cover_image:
            if request:
                return request.build_absolute_uri(obj.cover_image.url)
            return obj.cover_image.url
        return None


class CommunityDetailSerializer(CommunityListSerializer):
    members = serializers.SerializerMethodField()
    inviteLink = serializers.SerializerMethodField()

    class Meta(CommunityListSerializer.Meta):
        fields = CommunityListSerializer.Meta.fields + ['members', 'inviteLink']

    def get_members(self, obj):
        membership_qs = obj.members.select_related('user').order_by('joined_at')[:30]
        return MemberUserSerializer(membership_qs, many=True, context=self.context).data

    def get_inviteLink(self, obj):
        request = self.context.get('request')
        if not request:
            return None
        is_admin = obj.members.filter(user=request.user, role='admin').exists()
        if obj.privacy == 'private' and is_admin:
            return obj.invite_token
        return None


class CreateCommunitySerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120)
    description = serializers.CharField(required=False, allow_blank=True, default='')
    community_type = serializers.ChoiceField(choices=['general', 'book'])
    privacy = serializers.ChoiceField(choices=['public', 'private'])
    book_id = serializers.UUIDField(required=False, allow_null=True)
    cover_emoji = serializers.CharField(max_length=10, required=False, default='📚')

    def validate(self, data):
        if data.get('community_type') == 'book' and not data.get('book_id'):
            raise serializers.ValidationError({'book_id': 'Book ID required for book communities.'})
        return data


class SendMessageSerializer(serializers.Serializer):
    content = serializers.CharField(min_length=1, max_length=2000)
    reply_to_id = serializers.UUIDField(required=False, allow_null=True)


class ToggleReactionSerializer(serializers.Serializer):
    emoji = serializers.CharField(max_length=10)