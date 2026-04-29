import uuid
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.conf import settings


class UserManager(BaseUserManager):
    """
    Custom manager because we use email as login,
    not username like Django's default.
    """

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Email is required')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)  # Hashes the password automatically
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """
    Custom User model.
    Matches your Flutter UserEntity: { id, name, email }
    Plus auth fields Django needs.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=150, blank=True)
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True)

    # Google OAuth
    google_id = models.CharField(max_length=255, blank=True, null=True, unique=True)

    # Stats (mirrors your UserProfileEntity)
    books_read = models.PositiveIntegerField(default=0)
    total_pages_read = models.PositiveIntegerField(default=0)
    current_streak = models.PositiveIntegerField(default=0)
    is_avid_reader = models.BooleanField(default=False)

    # Django required fields
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    # Use email to log in instead of username
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['full_name']

    def __str__(self):
        return self.email

    @property
    def name(self):
        """
        Flutter uses 'name', Django uses 'full_name'.
        This property lets us access user.name anywhere.
        """
        return self.full_name


class PasswordResetOTP(models.Model):
    """
    Stores the 4-digit OTP for your forgot password flow.
    Matches your OtpVerificationPage which expects a 4-digit code.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='otps')
    code = models.CharField(max_length=4)
    created_at = models.DateTimeField(auto_now_add=True)
    is_used = models.BooleanField(default=False)

    def is_expired(self):
        """OTP expires after 2 minutes — matches your frontend timer"""
        from django.utils import timezone
        from datetime import timedelta
        return timezone.now() > self.created_at + timedelta(minutes=2)

    def __str__(self):
        return f"OTP for {self.user.email}"