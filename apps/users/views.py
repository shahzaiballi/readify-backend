import random
from django.core.mail import send_mail
from django.conf import settings
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError

from .models import User, PasswordResetOTP
from .serializers import (
    UserSerializer, RegisterSerializer, LoginSerializer,
    ForgotPasswordSerializer, VerifyOTPSerializer,
    ResetPasswordSerializer, UpdateProfileSerializer,
    GoogleAuthSerializer,
     UserProfileSerializer,      # new
    ChangePasswordSerializer,   # new
)



def get_tokens_for_user(user):
    """
    Helper: generate JWT access + refresh tokens for a user.
    This is what Flutter stores in secure storage.
    """
    refresh = RefreshToken.for_user(user)
    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
    }


class RegisterView(APIView):
    """
    POST /api/v1/auth/register/
    Matches your SignUpPage — creates account, returns tokens immediately
    so the user doesn't have to log in separately after registering.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)

        if serializer.is_valid():
            user = serializer.save()
            tokens = get_tokens_for_user(user)

            return Response({
                'user': UserSerializer(user).data,
                'tokens': tokens,
                'message': 'Account created successfully.'
            }, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LoginView(APIView):
    """
    POST /api/v1/auth/login/
    Matches your LoginPage — email + password → tokens
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)

        if serializer.is_valid():
            user = serializer.validated_data['user']
            tokens = get_tokens_for_user(user)

            return Response({
                'user': UserSerializer(user).data,
                'tokens': tokens,
            }, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class GoogleAuthView(APIView):
    """
    POST /api/v1/auth/google/
    Flutter sends the Google ID token.
    We verify it and either find or create the user.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = GoogleAuthSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        id_token = serializer.validated_data['id_token']

        try:
            # Verify the Google token
            # This requires: pip install google-auth
            from google.oauth2 import id_token as google_id_token
            from google.auth.transport import requests as google_requests

            google_client_id = settings.GOOGLE_CLIENT_ID
            id_info = google_id_token.verify_oauth2_token(
                id_token,
                google_requests.Request(),
                google_client_id
            )

            google_user_id = id_info['sub']
            email = id_info['email']
            name = id_info.get('name', '')
            avatar = id_info.get('picture', '')

            # Find existing user or create new one
            user, created = User.objects.get_or_create(
                email=email,
                defaults={
                    'full_name': name,
                    'avatar_url': avatar,
                    'google_id': google_user_id,
                }
            )

            # If user exists but doesn't have google_id yet, link it
            if not created and not user.google_id:
                user.google_id = google_user_id
                user.save()

            tokens = get_tokens_for_user(user)

            return Response({
                'user': UserSerializer(user).data,
                'tokens': tokens,
                'is_new_user': created,
            }, status=status.HTTP_200_OK)

        except ValueError as e:
            return Response(
                {'error': 'Invalid Google token. Please try again.'},
                status=status.HTTP_400_BAD_REQUEST
            )


class LogoutView(APIView):
    """
    POST /api/v1/auth/logout/
    Blacklists the refresh token so it can't be reused.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get('refresh')

        if not refresh_token:
            return Response(
                {'error': 'Refresh token is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response({'message': 'Logged out successfully.'})
        except TokenError:
            return Response(
                {'error': 'Invalid or expired token.'},
                status=status.HTTP_400_BAD_REQUEST
            )


class MeView(APIView):
    """
    GET  /api/v1/auth/me/  → returns current user profile
    PATCH /api/v1/auth/me/ → update name, avatar
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = UserSerializer(request.user)
        return Response(serializer.data)

    def patch(self, request):
        serializer = UpdateProfileSerializer(
            request.user,
            data=request.data,
            partial=True  # Allow updating only some fields
        )
        if serializer.is_valid():
            serializer.save()
            return Response(UserSerializer(request.user).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ForgotPasswordView(APIView):
    """
    POST /api/v1/auth/forgot-password/
    Matches your ForgotPasswordPage — sends 4-digit OTP to email.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ForgotPasswordSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        email = serializer.validated_data['email'].lower()

        # Don't reveal whether email exists (security best practice)
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            # Return success anyway so attackers can't enumerate emails
            return Response({
                'message': 'If this email exists, a code has been sent.'
            })

        # Delete any existing unused OTPs for this user
        PasswordResetOTP.objects.filter(user=user, is_used=False).delete()

        # Generate a 4-digit code — matches your OtpVerificationPage
        code = str(random.randint(1000, 9999))
        PasswordResetOTP.objects.create(user=user, code=code)

        # Send email (prints to terminal in development)
        send_mail(
            subject='Your Readify password reset code',
            message=f'Your 4-digit reset code is: {code}\n\nThis code expires in 2 minutes.',
            from_email=settings.EMAIL_HOST_USER,
            recipient_list=[email],
            fail_silently=False,
        )

        return Response({'message': 'If this email exists, a code has been sent.'})


class VerifyOTPView(APIView):
    """
    POST /api/v1/auth/verify-otp/
    Matches your OtpVerificationPage — validates the 4-digit code.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = VerifyOTPSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        email = serializer.validated_data['email'].lower()
        code = serializer.validated_data['code']

        try:
            user = User.objects.get(email=email)
            otp = PasswordResetOTP.objects.filter(
                user=user,
                code=code,
                is_used=False
            ).latest('created_at')

            if otp.is_expired():
                return Response(
                    {'error': 'Code has expired. Please request a new one.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            return Response({'message': 'Code verified successfully.'})

        except (User.DoesNotExist, PasswordResetOTP.DoesNotExist):
            return Response(
                {'error': 'Invalid code. Please try again.'},
                status=status.HTTP_400_BAD_REQUEST
            )


class ResetPasswordView(APIView):
    """
    POST /api/v1/auth/reset-password/
    Called after OTP is verified — sets the new password.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ResetPasswordSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        email = serializer.validated_data['email'].lower()
        code = serializer.validated_data['code']
        new_password = serializer.validated_data['new_password']

        try:
            user = User.objects.get(email=email)
            otp = PasswordResetOTP.objects.filter(
                user=user,
                code=code,
                is_used=False
            ).latest('created_at')

            if otp.is_expired():
                return Response(
                    {'error': 'Code has expired. Please request a new one.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Set new password
            user.set_password(new_password)
            user.save()

            # Mark OTP as used so it can't be reused
            otp.is_used = True
            otp.save()

            return Response({'message': 'Password reset successfully.'})

        except (User.DoesNotExist, PasswordResetOTP.DoesNotExist):
            return Response(
                {'error': 'Invalid request.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
class UserProfileView(APIView):
    """
    GET   /api/v1/auth/profile/  → full profile with stats + achievements
    PATCH /api/v1/auth/profile/  → update name or avatar
    Matches your UserProfileEntity and ProfilePage.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Sync isAvidReader flag based on books_read count
        if request.user.books_read >= 5 and not request.user.is_avid_reader:
            request.user.is_avid_reader = True
            request.user.save(update_fields=['is_avid_reader'])

        serializer = UserProfileSerializer(request.user)
        return Response(serializer.data)

    def patch(self, request):
        serializer = UpdateProfileSerializer(
            request.user,
            data=request.data,
            partial=True,
        )
        if serializer.is_valid():
            serializer.save()
            # Return full profile after update
            return Response(UserProfileSerializer(request.user).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ChangePasswordView(APIView):
    """
    POST /api/v1/auth/change-password/
    Requires the user to be logged in.
    Matches your change password flow.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(
            data=request.data,
            context={'request': request},
        )

        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Set the new password
        request.user.set_password(serializer.validated_data['new_password'])
        request.user.save()

        # Invalidate all existing tokens — user must log in again
        # This is a security best practice after password change
        try:
            refresh_token = request.data.get('refresh_token')
            if refresh_token:
                from rest_framework_simplejwt.tokens import RefreshToken
                token = RefreshToken(refresh_token)
                token.blacklist()
        except Exception:
            pass  # Don't block the response if blacklisting fails

        return Response({
            'message': 'Password changed successfully. Please log in again.',
        })


class UpdateStatsView(APIView):
    """
    POST /api/v1/auth/stats/update/
    Called internally when a book is completed or pages are read.
    Updates booksRead, totalPages, currentStreak on the User model.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        books_read_delta = request.data.get('books_read_delta', 0)
        pages_read_delta = request.data.get('pages_read_delta', 0)

        user = request.user
        user.books_read += books_read_delta
        user.total_pages_read += pages_read_delta

        # Update isAvidReader automatically
        if user.books_read >= 5:
            user.is_avid_reader = True

        user.save(update_fields=[
            'books_read', 'total_pages_read', 'is_avid_reader'
        ])

        return Response(UserProfileSerializer(user).data)