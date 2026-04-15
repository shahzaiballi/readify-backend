import uuid
from django.db import models
from django.conf import settings


class ReadingSession(models.Model):
    """
    Records each time a user reads.
    Used to calculate dayStreak and readTodayMinutes for InsightsEntity.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    user_book = models.ForeignKey(
        'library.UserBook',
        on_delete=models.CASCADE,
        related_name='reading_sessions'
    )
    last_chunk = models.ForeignKey(
        'books.Chunk',
        on_delete=models.SET_NULL,
        null=True, blank=True
    )

    chunks_completed = models.PositiveIntegerField(default=0)
    duration_seconds = models.PositiveIntegerField(default=0)
    session_date = models.DateField(auto_now_add=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Session: {self.user_book} on {self.session_date}"


class ReadingPlan(models.Model):
    """
    Matches your ReadingPlanEntity exactly.
    One plan per user.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='reading_plan'
    )
    daily_minutes = models.PositiveIntegerField(default=45)
    days_per_week = models.PositiveIntegerField(default=5)
    preferred_time = models.CharField(max_length=20, default='Evening')

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Plan: {self.user.email}"