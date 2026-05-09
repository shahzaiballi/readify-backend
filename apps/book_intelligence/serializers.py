"""
apps/book_intelligence/serializers.py
"""

from rest_framework import serializers
from .models import (
    BookIntelligenceProfile,
    BookIntelligenceChapter,
    ChapterIntelligence,
    NotificationContent,
    QAConversation,
    QAMessage,
)


class BookIntelligenceProfileSerializer(serializers.ModelSerializer):
    book_title = serializers.CharField(source='book.title', read_only=True)
    book_author = serializers.CharField(source='book.author', read_only=True)

    class Meta:
        model = BookIntelligenceProfile
        fields = [
            'id', 'book_title', 'book_author',
            'book_type', 'detected_language', 'complexity_level',
            'status', 'embeddings_built', 'created_at',
        ]


class BookIntelligenceChapterSerializer(serializers.ModelSerializer):
    class Meta:
        model = BookIntelligenceChapter
        fields = [
            'id', 'chapter_number', 'title',
            'start_page', 'end_page', 'page_range_display',
            'chapter_hook', 'user_confirmed',
        ]


class BookIntelligenceChapterUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = BookIntelligenceChapter
        fields = ['title', 'chapter_hook', 'user_confirmed']


class ChapterIntelligenceSerializer(serializers.ModelSerializer):
    chapter_title = serializers.CharField(source='ai_chapter.title', read_only=True)
    chapter_number = serializers.IntegerField(source='ai_chapter.chapter_number', read_only=True)

    class Meta:
        model = ChapterIntelligence
        fields = ['id', 'chapter_title', 'chapter_number', 'mode', 'content', 'generated_at']


class BookBriefSerializer(serializers.Serializer):
    """Serializes the cached book brief JSON."""
    what_its_about = serializers.CharField()
    who_its_for = serializers.CharField()
    core_argument = serializers.CharField()
    top_5_ideas = serializers.ListField(child=serializers.CharField())
    verdict = serializers.CharField()
    time_to_read_hours = serializers.IntegerField(default=6)


class NotificationContentSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationContent
        fields = [
            'id', 'date', 'chapter_number',
            'morning_hook', 'midday_concept',
            'afternoon_story', 'evening_recap',
            'generated_at',
        ]


class QAMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = QAMessage
        fields = ['id', 'question', 'answer', 'source_pages', 'created_at']


class QAConversationSerializer(serializers.ModelSerializer):
    messages = QAMessageSerializer(many=True, read_only=True)
    book_title = serializers.CharField(source='profile.book.title', read_only=True)

    class Meta:
        model = QAConversation
        fields = ['id', 'book_title', 'messages', 'created_at', 'updated_at']


class AskQuestionSerializer(serializers.Serializer):
    question = serializers.CharField(max_length=500)
