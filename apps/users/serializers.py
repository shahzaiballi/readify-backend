from rest_framework import serializers
from django.contrib.auth import authenticate
from .models import User


class UserSerializer(serializers.ModelSerializer):
    """
    What gets sent to Flutter after login/register.
    Matches your Flutter UserEntity exactly.
    """
    name = serializers.CharField(source='full_name', read_only=True)

    class Meta:
        model = User
        fields = ['id', 'name', 'email', 'avatar_url',
                  'books_read', 'total_pages_read',
                  'current_streak', 'is_avid_reader', 'created_at']
        read_only_fields = ['id', 'created_at', 'books_read',
                           'total_pages_read', 'current_streak']


class RegisterSerializer(serializers.ModelSerializer):
    """
    Matches your SignUpPage fields:
    full_name, email, password, confirm_password
    """
    password = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ['full_name', 'email', 'password', 'confirm_password']

    def validate(self, data):
        # Check passwords match — same check your Flutter frontend does
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
    Matches your LoginPage: email + password
    """
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        email = data.get('email', '').lower()
        password = data.get('password')

        user = authenticate(username=email, password=password)

        if not user:
            raise serializers.ValidationError(
                'Invalid email or password. Please try again.'
            )
        if not user.is_active:
            raise serializers.ValidationError('This account has been deactivated.')

        data['user'] = user
        return data


class GoogleAuthSerializer(serializers.Serializer):
    """
    Matches your Flutter _handleGoogleSignIn().
    Flutter sends the Google ID token after sign-in.
    """
    id_token = serializers.CharField()


class ForgotPasswordSerializer(serializers.Serializer):
    """Matches your ForgotPasswordPage — just needs an email"""
    email = serializers.EmailField()


class VerifyOTPSerializer(serializers.Serializer):
    """
    Matches your OtpVerificationPage — 4-digit code.
    We also need the email to find the right user.
    """
    email = serializers.EmailField()
    code = serializers.CharField(max_length=4, min_length=4)


class ResetPasswordSerializer(serializers.Serializer):
    """Called after OTP verified — sets the new password"""
    email = serializers.EmailField()
    code = serializers.CharField(max_length=4)
    new_password = serializers.CharField(min_length=8, write_only=True)
    confirm_password = serializers.CharField(write_only=True)

    def validate(self, data):
        if data['new_password'] != data['confirm_password']:
            raise serializers.ValidationError({
                'confirm_password': 'Passwords do not match.'
            })
        return data


class UpdateProfileSerializer(serializers.ModelSerializer):
    """For PATCH /auth/me/ — update name and avatar"""
    class Meta:
        model = User
        fields = ['full_name', 'avatar_url']