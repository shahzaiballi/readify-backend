"""
apps/books/models.py

Book-related models for Readify.

Key additions vs original:
- Book.pdf_file       — stores the uploaded PDF (admin-uploaded books)
- Book.source         — 'admin' or 'user_upload', so we know where it came from
- Book.processing_status — tracks whether AI chunking is done
- UserUploadedBook    — when a USER uploads their own PDF from the Flutter app
"""

import uuid
from django.db import models
from django.conf import settings


import uuid
import os

def book_pdf_upload_path(instance, filename):
    ext = filename.split('.')[-1]
    return f'books/pdfs/{uuid.uuid4()}.{ext}'


def book_cover_upload_path(instance, filename):
    """Store cover images in media/books/covers/<book_id>/<filename>"""
    return f'books/covers/{instance.id}/{filename}'


def user_book_pdf_upload_path(instance, filename):
    ext = filename.split('.')[-1]
    return f'user_uploads/{instance.uploaded_by_id}/{uuid.uuid4()}.{ext}'


class Book(models.Model):
    """
    Central book model — covers both admin-curated books and user uploads.

    source='admin'       → uploaded by admin, shown in Recommended for all users
    source='user_upload' → uploaded by a specific user, only visible to them
    """

    class Source(models.TextChoices):
        ADMIN = 'admin', 'Admin Curated'
        USER_UPLOAD = 'user_upload', 'User Upload'

    class ProcessingStatus(models.TextChoices):
        PENDING = 'pending', 'Pending'
        PROCESSING = 'processing', 'Processing'
        COMPLETED = 'completed', 'Completed'
        FAILED = 'failed', 'Failed'

    class ReadingMode(models.TextChoices):
        SKIM = 'skim', 'Skim'
        CONCEPT = 'concept', 'Concept'
        DEEP = 'deep', 'Deep'
        EXAM = 'exam', 'Exam'

    class ChapterSource(models.TextChoices):
        BOOKMARKS = 'bookmarks', 'PDF Bookmarks'
        TEXT_TOC = 'text_toc', 'Text TOC'
        AI_GENERATED = 'ai_generated', 'AI Generated'
        MANUAL = 'manual', 'Manual Split'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    author = models.CharField(max_length=255)

    # Cover image — can be uploaded or a URL (for admin books)
    cover_image_url = models.URLField(blank=True, null=True)
    cover_image = models.ImageField(
        upload_to=book_cover_upload_path,
        blank=True,
        null=True,
        help_text='Upload a cover image (optional if cover_image_url is set)'
    )

    category = models.CharField(max_length=100)
    readers_count = models.PositiveIntegerField(default=0)
    rating = models.DecimalField(max_digits=3, decimal_places=1, default=0.0)
    has_audio = models.BooleanField(default=False)
    badge = models.CharField(max_length=10, blank=True, null=True)

    # Book detail fields
    description = models.TextField(blank=True)
    total_chapters = models.PositiveIntegerField(default=0)
    pages_left = models.PositiveIntegerField(default=0)
    flashcards_count = models.PositiveIntegerField(default=0)
    read_per_day_minutes = models.PositiveIntegerField(default=45)

    # ── PDF & Processing ──────────────────────────────────────────────────────
    # The actual PDF file (admin uploads via Django admin panel)
    pdf_file = models.FileField(
        upload_to=book_pdf_upload_path,
        max_length=255,
        blank=True,
        null=True,
        help_text='Upload the PDF of this book. Chapters and chunks will be auto-generated.'
    )

    # Where this book came from
    source = models.CharField(
        max_length=20,
        choices=Source.choices,
        default=Source.ADMIN,
    )

    # Tracks background AI chunking progress — shown in admin panel
    processing_status = models.CharField(
        max_length=20,
        choices=ProcessingStatus.choices,
        default=ProcessingStatus.PENDING,
    )
    processing_error = models.TextField(
        blank=True,
        help_text='Error message if processing failed'
    )

    # ── Visibility Flags ──────────────────────────────────────────────────────
    is_published = models.BooleanField(default=True)
    is_trending = models.BooleanField(default=False)
    is_recommended = models.BooleanField(
        default=False,
        help_text='Show in Recommended section for all users on home screen'
    )

    reading_mode = models.CharField(
        max_length=10,
        choices=ReadingMode.choices,
        default=ReadingMode.DEEP,
        help_text='User\'s chosen reading mode — drives which summaries are pre-generated',
    )
    daily_minutes = models.PositiveIntegerField(
        default=30,
        help_text='User\'s daily reading time in minutes (15/30/45/60)',
    )
    chapter_source = models.CharField(
        max_length=20,
        choices=ChapterSource.choices,
        default=ChapterSource.MANUAL,
        help_text='How chapters were detected for this book',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} — {self.author}"

    def get_cover_url(self):
        """
        Returns whichever cover is available.
        Prefers uploaded file over URL (so admin can override the URL).
        """
        if self.cover_image:
            return self.cover_image.url
        return self.cover_image_url or ''

    def formatted_readers_count(self):
        """3000000 → '3M', 1100000 → '1.1M', 890000 → '890K'"""
        count = self.readers_count
        if count >= 1_000_000:
            value = count / 1_000_000
            return f"{value:.1f}M".replace('.0M', 'M')
        elif count >= 1_000:
            value = count / 1_000
            return f"{value:.1f}K".replace('.0K', 'K')
        return str(count)


class Chapter(models.Model):
    """
    A chapter within a book.
    Auto-created by the PDF processing task (or manually in admin).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name='chapters')
    chapter_number = models.PositiveIntegerField()
    title = models.CharField(max_length=255)
    page_range = models.CharField(max_length=50, blank=True)
    duration_in_minutes = models.PositiveIntegerField(default=15)
    is_locked = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    start_page = models.PositiveIntegerField(null=True, blank=True)
    end_page = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ['chapter_number']
        unique_together = ['book', 'chapter_number']

    def __str__(self):
        return f"Ch.{self.chapter_number}: {self.title}"


class Chunk(models.Model):
    """
    A reading chunk — one session's worth of content.
    Auto-created by task_build_reading_schedule using daily_minutes-based formula.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    chapter = models.ForeignKey(Chapter, on_delete=models.CASCADE, related_name='chunks')
    chunk_index = models.PositiveIntegerField()
    text = models.TextField()
    estimated_minutes = models.PositiveIntegerField(default=2)
    day_number = models.PositiveIntegerField(
        default=1,
        help_text='Which reading day this chunk belongs to (1-indexed, sequential across all chapters)',
    )
    words_count = models.PositiveIntegerField(
        default=0,
        help_text='Precomputed word count for scheduling calculations',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['chunk_index']
        unique_together = ['chapter', 'chunk_index']

    def __str__(self):
        return f"Chunk {self.chunk_index} of {self.chapter}"


class Summary(models.Model):
    """Chapter summary with key takeaways. Auto-generated by Claude."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    chapter = models.OneToOneField(Chapter, on_delete=models.CASCADE, related_name='summary')
    title = models.CharField(max_length=255)
    summary_content = models.TextField()
    key_takeaways = models.JSONField(default=list)
    is_locked = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Summary: {self.chapter}"


class Flashcard(models.Model):
    """Flashcard for a book. Auto-generated by Claude from chapter content."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name='flashcards')
    question = models.TextField()
    answer = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"Flashcard: {self.question[:50]}"


class UserUploadedBook(models.Model):
    """
    Tracks a PDF that a specific user uploaded from the Flutter app.

    New pipeline flow:
    1. User uploads PDF (with reading_mode + daily_minutes) → PENDING
    2. task_extract_and_detect runs → chapters detected → AWAITING_CONFIRM
    3. User reviews chapters in Flutter → calls /chapters/confirm/ → SCHEDULING
    4. task_build_reading_schedule runs → chunks created → PROCESSING
    5. Book Brief + initial summaries generated → COMPLETED
    """

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending Processing'
        PROCESSING = 'processing', 'Processing'
        AWAITING_CONFIRM = 'awaiting_confirm', 'Awaiting Chapter Confirmation'
        SCHEDULING = 'scheduling', 'Building Reading Schedule'
        COMPLETED = 'completed', 'Completed'
        FAILED = 'failed', 'Failed'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='uploaded_books',
    )

    # User-provided metadata (from Flutter's AddBookPage form)
    title = models.CharField(max_length=255)
    author = models.CharField(max_length=255, blank=True)

    # The actual PDF file
    pdf_file = models.FileField(upload_to=user_book_pdf_upload_path, max_length=255)

    # Reading preferences (collected at upload time)
    reading_mode = models.CharField(
        max_length=10,
        choices=Book.ReadingMode.choices,
        default=Book.ReadingMode.DEEP,
    )
    daily_minutes = models.PositiveIntegerField(default=30)

    # TOC detection results (stored for review step)
    toc_raw = models.JSONField(
        default=list,
        blank=True,
        help_text='Raw detected chapters before user confirmation',
    )
    total_pages = models.PositiveIntegerField(
        default=0,
        help_text='Total PDF page count, set during Stage 1',
    )

    # Granular pipeline stage — Flutter polls this for detailed progress
    processing_stage = models.CharField(
        max_length=50,
        blank=True,
        default='',
        help_text='Current pipeline stage name for Flutter status polling',
    )

    # Processing state
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    error_message = models.TextField(blank=True)

    # Once processing is done, this points to the created Book record
    book = models.OneToOneField(
        Book,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='user_upload_source',
    )

    uploaded_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.uploaded_by.email}: {self.title} ({self.status})"


class ReadingSchedule(models.Model):
    """
    Stores the full reading calendar for a user+book combination.
    Created by task_build_reading_schedule after chapter confirmation.
    One record per user per book.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='reading_schedules',
    )
    book = models.ForeignKey(
        Book,
        on_delete=models.CASCADE,
        related_name='reading_schedules',
    )

    schedule_data = models.JSONField(
        default=list,
        help_text='List of {day, chunk_ids, estimated_minutes, chapter_number, chapter_title}',
    )
    total_days = models.PositiveIntegerField(default=0)
    start_date = models.DateField(
        help_text='When the user started this reading plan',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['user', 'book']
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user}: {self.book.title} ({self.total_days} days)"