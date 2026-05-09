from django.contrib import admin
from .models import (
    BookIntelligenceProfile,
    BookIntelligenceChapter,
    ChapterIntelligence,
    PageEmbedding,
    NotificationContent,
    QAConversation,
    QAMessage,
)


@admin.register(BookIntelligenceProfile)
class BookIntelligenceProfileAdmin(admin.ModelAdmin):
    list_display = ['book', 'book_type', 'status', 'embeddings_built', 'brief_ready', 'created_at']
    list_filter = ['status', 'book_type', 'complexity_level']
    search_fields = ['book__title']
    readonly_fields = ['id', 'created_at', 'updated_at', 'classification_raw', 'book_brief']

    def brief_ready(self, obj):
        return bool(obj.book_brief)
    brief_ready.boolean = True


@admin.register(BookIntelligenceChapter)
class BookIntelligenceChapterAdmin(admin.ModelAdmin):
    list_display = ['chapter_number', 'title', 'profile', 'start_page', 'end_page', 'user_confirmed']
    list_filter = ['user_confirmed']
    search_fields = ['title', 'profile__book__title']


@admin.register(ChapterIntelligence)
class ChapterIntelligenceAdmin(admin.ModelAdmin):
    list_display = ['ai_chapter', 'mode', 'generated_at']
    list_filter = ['mode']
    search_fields = ['ai_chapter__title']


@admin.register(PageEmbedding)
class PageEmbeddingAdmin(admin.ModelAdmin):
    list_display = ['profile', 'page_number', 'chunk_index', 'created_at']
    list_filter = ['profile__book__title']
    readonly_fields = ['embedding']  # Don't render 768-float vector in admin

    def has_add_permission(self, request):
        return False  # Embeddings are auto-generated


@admin.register(NotificationContent)
class NotificationContentAdmin(admin.ModelAdmin):
    list_display = ['user', 'profile', 'date', 'chapter_number', 'generated_at']
    list_filter = ['date']
    search_fields = ['user__email', 'profile__book__title']


@admin.register(QAConversation)
class QAConversationAdmin(admin.ModelAdmin):
    list_display = ['user', 'profile', 'created_at']
    search_fields = ['user__email', 'profile__book__title']


@admin.register(QAMessage)
class QAMessageAdmin(admin.ModelAdmin):
    list_display = ['conversation', 'question_preview', 'created_at']
    search_fields = ['question']

    def question_preview(self, obj):
        return obj.question[:60]
    question_preview.short_description = 'Question'
