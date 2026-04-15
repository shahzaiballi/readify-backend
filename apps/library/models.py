import uuid
from django.db import models
from django.conf import settings


class UserBook(models.Model):
    """
    The junction between a User and a Book.
    Matches your LibraryBookEntity: progressPercent, isFavorite, status.
    Also used for UserProgressEntity on the home screen.
    """

    class Status(models.TextChoices):
        NOT_STARTED = 'not_started', 'Not Started'
        IN_PROGRESS = 'in_progress', 'In Progress'
        COMPLETED = 'completed', 'Completed'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='user_books'
    )
    book = models.ForeignKey(
        'books.Book',
        on_delete=models.CASCADE,
        related_name='user_books'
    )

    progress_percent = models.PositiveIntegerField(default=0)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.NOT_STARTED
    )
    is_favorite = models.BooleanField(default=False)

    # Track which chapter and chunk the user is currently on
    current_chapter = models.ForeignKey(
        'books.Chapter',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='active_readers'
    )
    current_chunk_index = models.PositiveIntegerField(default=0)

    added_at = models.DateTimeField(auto_now_add=True)
    last_read_at = models.DateTimeField(auto_now=True)

    class Meta:
        # A user can only add a book to their library once
        unique_together = ['user', 'book']
        ordering = ['-last_read_at']

    def __str__(self):
        return f"{self.user.email} → {self.book.title}"


class ChapterProgress(models.Model):
    """
    Tracks whether a user has completed a specific chapter.
    Used to compute isCompleted and isActive on ChapterEntity.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    user_book = models.ForeignKey(
        UserBook,
        on_delete=models.CASCADE,
        related_name='chapter_progresses'
    )
    chapter = models.ForeignKey(
        'books.Chapter',
        on_delete=models.CASCADE,
        related_name='reading_progresses'
    )

    is_completed = models.BooleanField(default=False)
    is_active = models.BooleanField(default=False)
    last_chunk_index = models.PositiveIntegerField(default=0)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ['user_book', 'chapter']

    def __str__(self):
        return f"{self.user_book} — {self.chapter}"