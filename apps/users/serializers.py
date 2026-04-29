"""
apps/users/serializers.py

FIX for login 400 error:
The Flutter app sends { "email": "...", "password": "..." }
Django's authenticate() uses USERNAME_FIELD which is 'email',
but the default backend expects 'username'.

Fix: pass email directly to authenticate() and ensure the
custom backend is being used correctly.
"""

from rest_framework import serializers
from django.contrib.auth import authenticate
from .models import User


avatarUrl = serializers.SerializerMethodField()

class UserSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source='full_name', read_only=True)
    avatarUrl = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'name', 'email', 'avatarUrl',
            'books_read', 'total_pages_read',
            'current_streak', 'is_avid_reader', 'created_at'
        ]

    def get_avatarUrl(self, obj):
        request = self.context.get('request')
        if obj.avatar:
            if request:
                return request.build_absolute_uri(obj.avatar.url)
            return obj.avatar.url

        return f'https://i.pravatar.cc/150?u={obj.email}'


class RegisterSerializer(serializers.ModelSerializer):
    """
    Matches Flutter SignUpPage fields:
    full_name, email, password, confirm_password
    """
    password = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ['full_name', 'email', 'password', 'confirm_password']

    def validate(self, data):
        if data['password'] != data['confirm_password']:
            raise serializers.ValidationError({
                'confirm_password': 'Passwords do not match.'
            })
        return data

    def validate_email(self, value):
        if User.objects.filter(email=value.lower()).exists():
            raise serializers.ValidationError('An account with this email already exists.')
        return value.lower()

    def create(self, validated_data):
        validated_data.pop('confirm_password')
        user = User.objects.create_user(
            email=validated_data['email'],
            password=validated_data['password'],
            full_name=validated_data.get('full_name', ''),
        )
        return user


class LoginSerializer(serializers.Serializer):
    """
    Matches Flutter LoginPage: email + password.

    FIX: Django's authenticate() needs username=email when using
    a custom user model with USERNAME_FIELD = 'email'.
    We pass username=email so the ModelBackend finds the user correctly.
    """
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        email = data.get('email', '').lower().strip()
        password = data.get('password', '')

        if not email or not password:
            raise serializers.ValidationError('Email and password are required.')

        # Django's ModelBackend maps 'username' kwarg to USERNAME_FIELD
        # Since our USERNAME_FIELD = 'email', we pass username=email
        user = authenticate(
            request=self.context.get('request'),
            username=email,   # <-- this is the key fix
            password=password,
        )

        if not user:
            raise serializers.ValidationError(
                'Invalid email or password. Please try again.'
            )

        if not user.is_active:
            raise serializers.ValidationError('This account has been deactivated.')

        data['user'] = user
        return data


class AchievementSerializer(serializers.Serializer):
    """Matches AchievementEntity."""
    id = serializers.CharField()
    title = serializers.CharField()
    description = serializers.CharField()
    iconCode = serializers.CharField()
    isUnlocked = serializers.BooleanField()


class UserProfileSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source='full_name', read_only=True)
    avatarUrl = serializers.SerializerMethodField()

    booksRead = serializers.IntegerField(source='books_read', read_only=True)
    totalPages = serializers.IntegerField(source='total_pages_read', read_only=True)
    currentStreak = serializers.IntegerField(source='current_streak', read_only=True)
    isAvidReader = serializers.BooleanField(source='is_avid_reader', read_only=True)

    achievements = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'name', 'email', 'avatarUrl',
            'booksRead', 'totalPages', 'currentStreak',
            'isAvidReader', 'achievements',
        ]

    def get_avatarUrl(self, obj):
        request = self.context.get('request')
        if obj.avatar:
            if request:
                return request.build_absolute_uri(obj.avatar.url)
            return obj.avatar.url
        return f'https://i.pravatar.cc/150?u={obj.email}'

    def get_achievements(self, user):
        return [
            {
                'id': 'a1',
                'title': 'First Week Streak',
                'description': 'Read for 7 consecutive days',
                'iconCode': 'trophy',
                'isUnlocked': user.current_streak >= 7,
            },
            {
                'id': 'a2',
                'title': 'Bookworm',
                'description': 'Completed 10 books',
                'iconCode': 'books',
                'isUnlocked': user.books_read >= 10,
            },
            {
                'id': 'a3',
                'title': 'Consistent Reader',
                'description': 'Met daily goal 30 times',
                'iconCode': 'target',
                'isUnlocked': user.total_pages_read >= 1000,
            },
        ]

class ChangePasswordSerializer(serializers.Serializer):
    """POST /api/v1/auth/change-password/"""
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True)

    def validate(self, data):
        if data['new_password'] != data['confirm_password']:
            raise serializers.ValidationError({'confirm_password': 'Passwords do not match.'})
        return data

    def validate_current_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError('Current password is incorrect.')
        return value


class GoogleAuthSerializer(serializers.Serializer):
    """Matches Flutter _handleGoogleSignIn()."""
    id_token = serializers.CharField()


class ForgotPasswordSerializer(serializers.Serializer):
    """Matches ForgotPasswordPage."""
    email = serializers.EmailField()


class VerifyOTPSerializer(serializers.Serializer):
    """Matches OtpVerificationPage."""
    email = serializers.EmailField()
    code = serializers.CharField(max_length=4, min_length=4)


class ResetPasswordSerializer(serializers.Serializer):
    """Called after OTP verified."""
    email = serializers.EmailField()
    code = serializers.CharField(max_length=4)
    new_password = serializers.CharField(min_length=8, write_only=True)
    confirm_password = serializers.CharField(write_only=True)

    def validate(self, data):
        if data['new_password'] != data['confirm_password']:
            raise serializers.ValidationError({'confirm_password': 'Passwords do not match.'})
        return data


class UpdateProfileSerializer(serializers.ModelSerializer):
    """For PATCH /api/v1/auth/me/ and PATCH /api/v1/auth/profile/"""
    class Meta:
        model = User
        fields = ['full_name']