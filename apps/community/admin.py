from django.contrib import admin
from .models import Community, CommunityMember, Message, MessageReaction


@admin.register(Community)
class CommunityAdmin(admin.ModelAdmin):
    list_display = ('name', 'community_type', 'privacy', 'member_count', 'created_by', 'created_at')
    list_filter = ('community_type', 'privacy')
    search_fields = ('name', 'created_by__email')
    readonly_fields = ('invite_token', 'created_at', 'updated_at')


@admin.register(CommunityMember)
class CommunityMemberAdmin(admin.ModelAdmin):
    list_display = ('community', 'user', 'role', 'joined_at')
    list_filter = ('role',)
    search_fields = ('community__name', 'user__email')


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('community', 'sender', 'content_preview', 'is_deleted', 'created_at')
    list_filter = ('is_deleted',)
    search_fields = ('community__name', 'sender__email', 'content')

    def content_preview(self, obj):
        return obj.content[:60] + '...' if len(obj.content) > 60 else obj.content
    content_preview.short_description = 'Content'


@admin.register(MessageReaction)
class MessageReactionAdmin(admin.ModelAdmin):
    list_display = ('message', 'user', 'emoji', 'created_at')