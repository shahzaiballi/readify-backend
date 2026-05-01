"""
apps/community/models.py

Community Groups feature for Readify.

Two types of communities:
  - General: not tied to a specific book
  - Book-specific: tied to a Book (discovered via book search)

Privacy:
  - Public: anyone can search & join
  - Private: invite-link only, listed only in creator's private tab
"""

import uuid
import secrets
from django.db import models
from django.conf import settings


class Community(models.Model):
    class CommunityType(models.TextChoices):
        GENERAL = 'general', 'General'
        BOOK = 'book', 'Book Group'

    class Privacy(models.TextChoices):
        PUBLIC = 'public', 'Public'
        PRIVATE = 'private', 'Private'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    community_type = models.CharField(
        max_length=10, choices=CommunityType.choices, default=CommunityType.GENERAL
    )
    privacy = models.CharField(
        max_length=10, choices=Privacy.choices, default=Privacy.PUBLIC
    )

    # Creator
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='created_communities',
    )

    # Optional book link (for book-specific groups)
    book = models.ForeignKey(
        'books.Book',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='communities',
    )

    # Cover image / avatar
    cover_image = models.ImageField(upload_to='communities/covers/', null=True, blank=True)
    cover_emoji = models.CharField(max_length=10, blank=True, default='📚')

    # Invite link token (for private groups)
    invite_token = models.CharField(max_length=32, unique=True, blank=True)

    # Cached member count
    member_count = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'Communities'

    def save(self, *args, **kwargs):
        if not self.invite_token:
            self.invite_token = secrets.token_urlsafe(20)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.privacy})"

    @property
    def invite_link(self):
        return f"/community/join/{self.invite_token}"


class CommunityMember(models.Model):
    class Role(models.TextChoices):
        ADMIN = 'admin', 'Admin'
        MEMBER = 'member', 'Member'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    community = models.ForeignKey(
        Community, on_delete=models.CASCADE, related_name='members'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='community_memberships',
    )
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.MEMBER)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['community', 'user']
        ordering = ['joined_at']

    def __str__(self):
        return f"{self.user.email} in {self.community.name}"


class Message(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    community = models.ForeignKey(
        Community, on_delete=models.CASCADE, related_name='messages'
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='community_messages',
    )
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    edited_at = models.DateTimeField(null=True, blank=True)
    is_deleted = models.BooleanField(default=False)

    # Reply threading (optional)
    reply_to = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='replies'
    )

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"[{self.community.name}] {self.sender.email}: {self.content[:40]}"


class MessageReaction(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    message = models.ForeignKey(
        Message, on_delete=models.CASCADE, related_name='reactions'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='message_reactions',
    )
    emoji = models.CharField(max_length=10)  # e.g. "❤️", "👍", "🔥"
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['message', 'user', 'emoji']

    def __str__(self):
        return f"{self.emoji} by {self.user.email} on msg {self.message.id}"