import uuid
from django.db import models


class Book(models.Model):
    """
    Matches your BookEntity and BookDetailEntity.
    Single model covers both — detail fields are just nullable for list views.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    author = models.CharField(max_length=255)
    cover_image_url = models.URLField(blank=True, null=True)
    category = models.CharField(max_length=100)

    # Stored as integer, formatted to "3M", "1.1M" etc. in serializer
    readers_count = models.PositiveIntegerField(default=0)
    rating = models.DecimalField(max_digits=3, decimal_places=1, default=0.0)

    has_audio = models.BooleanField(default=False)

    # Badge like "#1", "#2" for trending
    badge = models.CharField(max_length=10, blank=True, null=True)

    # Detail fields (used in BookDetailPage)
    description = models.TextField(blank=True)
    total_chapters = models.PositiveIntegerField(default=0)
    pages_left = models.PositiveIntegerField(default=0)
    flashcards_count = models.PositiveIntegerField(default=0)
    read_per_day_minutes = models.PositiveIntegerField(default=45)

    # Visibility
    is_published = models.BooleanField(default=True)
    is_trending = models.BooleanField(default=False)
    is_recommended = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} — {self.author}"

    def formatted_readers_count(self):
        """
        Converts integer to Flutter-matching string.
        3000000 → "3M", 1100000 → "1.1M", 890000 → "890K"
        """
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
    Matches your ChapterEntity exactly.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    book = models.ForeignKey(
        Book,
        on_delete=models.CASCADE,
        related_name='chapters'
    )
    chapter_number = models.PositiveIntegerField()
    title = models.CharField(max_length=255)
    page_range = models.CharField(max_length=50, blank=True)
    duration_in_minutes = models.PositiveIntegerField(default=15)
    is_locked = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['chapter_number']
        # A book can't have two chapters with the same number
        unique_together = ['book', 'chapter_number']

    def __str__(self):
        return f"Ch.{self.chapter_number}: {self.title}"


class Chunk(models.Model):
    """
    Matches your ChunkEntity.
    A chapter is broken into multiple readable chunks (2-5 min each).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    chapter = models.ForeignKey(
        Chapter,
        on_delete=models.CASCADE,
        related_name='chunks'
    )
    chunk_index = models.PositiveIntegerField()
    text = models.TextField()
    estimated_minutes = models.PositiveIntegerField(default=2)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['chunk_index']
        unique_together = ['chapter', 'chunk_index']

    def __str__(self):
        return f"Chunk {self.chunk_index} of {self.chapter}"


class Summary(models.Model):
    """
    Matches your SummaryEntity.
    One summary per chapter with key takeaways stored as JSON array.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    chapter = models.OneToOneField(
        Chapter,
        on_delete=models.CASCADE,
        related_name='summary'
    )
    # chapter_number is derived from chapter FK, not stored separately
    title = models.CharField(max_length=255)
    summary_content = models.TextField()

    # Stored as JSON list: ["Takeaway 1", "Takeaway 2", ...]
    # Matches your Flutter List<String> keyTakeaways
    key_takeaways = models.JSONField(default=list)
    is_locked = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Summary: {self.chapter}"


class Flashcard(models.Model):
    """
    Matches your FlashcardEntity.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    book = models.ForeignKey(
        Book,
        on_delete=models.CASCADE,
        related_name='flashcards'
    )
    question = models.TextField()
    answer = models.TextField()

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"Flashcard: {self.question[:50]}"