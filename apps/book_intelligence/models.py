"""
apps/book_intelligence/models.py

All models for the Book Intelligence Agent feature.
Completely isolated from existing apps — no changes to apps/books.

Models:
  BookIntelligenceProfile  — master record per Book: classification, brief, status
  BookIntelligenceChapter  — AI-detected semantic chapter structure
  ChapterIntelligence      — per-chapter summaries for all 4 reading modes
  PageEmbedding            — stored text embeddings for RAG (cosine similarity)
  NotificationContent      — 4 daily notification pieces per user/book/day
  QAConversation           — Q&A session per user/book
  QAMessage                — individual question + answer pairs
"""

import uuid
from django.db import models
from django.conf import settings


class BookIntelligenceProfile(models.Model):
    """
    Master intelligence record for a book.
    Created after the book's PDF has been processed.
    One per Book (OneToOne).
    """

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        CLASSIFYING = 'classifying', 'Classifying'
        STRUCTURING = 'structuring', 'Detecting Structure'
        EMBEDDING = 'embedding', 'Building RAG Index'
        READY = 'ready', 'Ready'
        FAILED = 'failed', 'Failed'

    class BookType(models.TextChoices):
        SELF_HELP = 'self_help', 'Self Help'
        ACADEMIC = 'academic', 'Academic'
        FICTION = 'fiction', 'Fiction'
        TECHNICAL = 'technical', 'Technical'
        BIOGRAPHY = 'biography', 'Biography'
        BUSINESS = 'business', 'Business'
        OTHER = 'other', 'Other'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Link to the existing Book model (read-only reference — we never modify it)
    book = models.OneToOneField(
        'books.Book',
        on_delete=models.CASCADE,
        related_name='intelligence_profile',
    )

    # ── Classification ───────────────────────────────────────────────────────
    book_type = models.CharField(
        max_length=20, choices=BookType.choices, default=BookType.OTHER
    )
    detected_language = models.CharField(max_length=50, default='English')
    complexity_level = models.CharField(
        max_length=20,
        choices=[('beginner', 'Beginner'), ('intermediate', 'Intermediate'), ('advanced', 'Advanced')],
        default='intermediate',
    )
    classification_raw = models.JSONField(
        default=dict,
        help_text='Full classification response from DeepSeek',
    )

    # ── Book Brief (generated once, cached forever) ──────────────────────────
    book_brief = models.JSONField(
        null=True, blank=True,
        help_text='Cached Book Brief: what, who, core argument, top 5 ideas, verdict',
    )
    brief_generated_at = models.DateTimeField(null=True, blank=True)

    # ── Processing State ─────────────────────────────────────────────────────
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    error_message = models.TextField(blank=True)
    embeddings_built = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Book Intelligence Profile'

    def __str__(self):
        return f"Intelligence: {self.book.title} [{self.status}]"


class BookIntelligenceChapter(models.Model):
    """
    AI-detected semantic chapter (may differ from structural chapters in apps.books).
    The user can review and rename these via the API.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    profile = models.ForeignKey(
        BookIntelligenceProfile,
        on_delete=models.CASCADE,
        related_name='ai_chapters',
    )

    chapter_number = models.PositiveIntegerField()
    title = models.CharField(max_length=255)
    start_page = models.PositiveIntegerField(default=1)
    end_page = models.PositiveIntegerField(default=1)
    page_range_display = models.CharField(max_length=50, blank=True)

    # Brief description of what this chapter is about (short, ~1 sentence)
    chapter_hook = models.TextField(blank=True)

    # Whether user has confirmed/edited this chapter
    user_confirmed = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['chapter_number']
        unique_together = ['profile', 'chapter_number']

    def __str__(self):
        return f"Ch.{self.chapter_number}: {self.title}"


class ChapterIntelligence(models.Model):
    """
    Per-chapter AI-generated content for each of the 4 reading modes.
    Generated lazily when user first accesses that chapter in that mode.
    Cached permanently — never regenerated unless explicitly reset.
    """

    class ReadingMode(models.TextChoices):
        SKIM = 'skim', 'Skim Mode'
        CONCEPT = 'concept', 'Concept Mode'
        DEEP = 'deep', 'Deep Mode'
        EXAM = 'exam', 'Exam Mode'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    ai_chapter = models.ForeignKey(
        BookIntelligenceChapter,
        on_delete=models.CASCADE,
        related_name='intelligence_by_mode',
    )

    mode = models.CharField(max_length=10, choices=ReadingMode.choices)

    # Content varies by mode — stored as JSON for flexibility:
    # skim:    {"one_liner": "..."}
    # concept: {"concepts": [{"name": "...", "description": "..."}]}
    # deep:    {"breakdown": "...", "examples": [...], "analogy": "..."}
    # exam:    {"qa_pairs": [{"question": "...", "answer": "..."}]}
    content = models.JSONField(default=dict)

    generated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['ai_chapter', 'mode']

    def __str__(self):
        return f"{self.ai_chapter} [{self.mode}]"


class PageEmbedding(models.Model):
    """
    Stores text + embedding vector for RAG (Ask Your Book).
    One record per chunk/page of the book.
    Embedding is stored as a JSON list of floats (cosine similarity in Python).
    No pgvector required — works with pure numpy.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    profile = models.ForeignKey(
        BookIntelligenceProfile,
        on_delete=models.CASCADE,
        related_name='page_embeddings',
    )

    page_number = models.PositiveIntegerField()
    chunk_index = models.PositiveIntegerField(default=0)
    text_content = models.TextField()

    # Embedding as JSON array of floats (768-dim for Gemini text-embedding-004)
    embedding = models.JSONField(default=list)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['page_number', 'chunk_index']

    def __str__(self):
        return f"Embedding p{self.page_number}.{self.chunk_index} [{self.profile.book.title}]"


class NotificationContent(models.Model):
    """
    4 daily notification pieces for a user/book/day combination.
    Generated in a single DeepSeek call. Stored in DB, served via API.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='book_notifications',
    )
    profile = models.ForeignKey(
        BookIntelligenceProfile,
        on_delete=models.CASCADE,
        related_name='notifications',
    )

    date = models.DateField()

    # The 4 timed notification pieces
    morning_hook = models.TextField(blank=True, help_text='7-9am: big idea in 1 sentence')
    midday_concept = models.TextField(blank=True, help_text='12-1pm: key concept or fact')
    afternoon_story = models.TextField(blank=True, help_text='3-5pm: quote, analogy, or story')
    evening_recap = models.TextField(blank=True, help_text='8-10pm: what you learned today')

    # Which chunk/chapter this day covers
    chapter_number = models.PositiveIntegerField(default=1)

    generated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['user', 'profile', 'date']
        ordering = ['-date']

    def __str__(self):
        return f"Notifications: {self.user.email} | {self.profile.book.title} | {self.date}"


class QAConversation(models.Model):
    """Tracks a Q&A session between a user and a book."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='book_qa_sessions',
    )
    profile = models.ForeignKey(
        BookIntelligenceProfile,
        on_delete=models.CASCADE,
        related_name='qa_conversations',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['user', 'profile']
        ordering = ['-updated_at']

    def __str__(self):
        return f"Q&A: {self.user.email} ↔ {self.profile.book.title}"


class QAMessage(models.Model):
    """Individual question + grounded answer pair."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    conversation = models.ForeignKey(
        QAConversation,
        on_delete=models.CASCADE,
        related_name='messages',
    )

    question = models.TextField()
    answer = models.TextField()

    # Pages used as context for this answer
    source_pages = models.JSONField(default=list, help_text='Page numbers used for RAG context')

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"Q: {self.question[:60]}"
