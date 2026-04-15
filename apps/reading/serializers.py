from rest_framework import serializers
from .models import ReadingSession, ReadingPlan


class ReadingPlanSerializer(serializers.ModelSerializer):
    """
    Matches your ReadingPlanEntity.
    Used by ReadingPlanPage and readingPlanProvider.
    """
    dailyMinutes = serializers.IntegerField(source='daily_minutes')
    daysPerWeek = serializers.IntegerField(source='days_per_week')
    preferredTime = serializers.CharField(source='preferred_time')

    class Meta:
        model = ReadingPlan
        fields = ['dailyMinutes', 'daysPerWeek', 'preferredTime']


class ReadingSessionSerializer(serializers.ModelSerializer):
    """Used to create or update a reading session."""
    userBookId = serializers.UUIDField(source='user_book.id', read_only=True)
    lastChunkId = serializers.UUIDField(
        source='last_chunk.id',
        read_only=True,
        allow_null=True
    )
    chunksCompleted = serializers.IntegerField(source='chunks_completed')
    durationSeconds = serializers.IntegerField(source='duration_seconds')

    class Meta:
        model = ReadingSession
        fields = [
            'id', 'userBookId', 'lastChunkId',
            'chunksCompleted', 'durationSeconds', 'session_date'
        ]


class CreateSessionSerializer(serializers.Serializer):
    """POST /reading/session/ — start or record a reading session"""
    book_id = serializers.UUIDField()
    chapter_id = serializers.UUIDField()
    chunk_index = serializers.IntegerField(min_value=0)
    duration_seconds = serializers.IntegerField(min_value=0, default=0)
    chunks_completed = serializers.IntegerField(min_value=0, default=0)


class InsightsSerializer(serializers.Serializer):
    """
    Matches your InsightsEntity exactly.
    cardsDue, readTodayMinutes, dayStreak
    """
    cardsDue = serializers.IntegerField()
    readTodayMinutes = serializers.IntegerField()
    dayStreak = serializers.IntegerField()