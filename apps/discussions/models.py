import uuid
from django.db import models
from django.conf import settings


class Post(models.Model):
    """
    Matches your PostEntity exactly.
    A discussion post tied to a book, optionally to a chapter.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='posts',
    )
    book = models.ForeignKey(
        'books.Book',
        on_delete=models.CASCADE,
        related_name='posts',
        null=True,
        blank=True,
    )

    # Matches your chapterTag field e.g. "Chapter 3"
    chapter_tag = models.CharField(max_length=50, blank=True)

    title = models.CharField(max_length=255)
    content = models.TextField()

    # Cached counts — updated when likes/replies are added
    # Avoids expensive COUNT queries on every list request
    likes_count = models.PositiveIntegerField(default=0)
    comments_count = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.email}: {self.title[:50]}"


class Reply(models.Model):
    """
    Matches your ReplyEntity exactly.
    A reply to a Post.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    post = models.ForeignKey(
        Post,
        on_delete=models.CASCADE,
        related_name='replies',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='replies',
    )

    content = models.TextField()
    likes_count = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"Reply by {self.user.email} on {self.post.title[:30]}"


class PostLike(models.Model):
    """
    Tracks which users liked which posts.
    Prevents duplicate likes and lets us toggle them.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='post_likes',
    )
    post = models.ForeignKey(
        Post,
        on_delete=models.CASCADE,
        related_name='post_likes',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # A user can only like a post once
        unique_together = ['user', 'post']

    def __str__(self):
        return f"{self.user.email} liked {self.post.title[:30]}"


class ReplyLike(models.Model):
    """
    Tracks which users liked which replies.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='reply_likes',
    )
    reply = models.ForeignKey(
        Reply,
        on_delete=models.CASCADE,
        related_name='reply_likes',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['user', 'reply']

    def __str__(self):
        return f"{self.user.email} liked reply {self.reply.id}"