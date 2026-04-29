import random
from django.core.mail import send_mail
from django.conf import settings
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework.parsers import MultiPartParser, FormParser

from .models import User, PasswordResetOTP
from .serializers import (
    UserSerializer, RegisterSerializer, LoginSerializer,
    ForgotPasswordSerializer, VerifyOTPSerializer,
    ResetPasswordSerializer, UpdateProfileSerializer,
    GoogleAuthSerializer, UserProfileSerializer,
    ChangePasswordSerializer,
)


# 🔑 JWT helper
def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
    }


# 🟢 REGISTER
class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)

        if serializer.is_valid():
            user = serializer.save()
            tokens = get_tokens_for_user(user)

            return Response({
                'user': UserSerializer(user, context={'request': request}).data,
                'tokens': tokens,
                'message': 'Account created successfully.'
            }, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# 🟢 LOGIN
class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)

        if serializer.is_valid():
            user = serializer.validated_data['user']
            tokens = get_tokens_for_user(user)

            return Response({
                'user': UserSerializer(user, context={'request': request}).data,
                'tokens': tokens,
            }, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# 🟢 GOOGLE AUTH
class GoogleAuthView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = GoogleAuthSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        id_token = serializer.validated_data['id_token']

        try:
            from google.oauth2 import id_token as google_id_token
            from google.auth.transport import requests as google_requests

            id_info = google_id_token.verify_oauth2_token(
                id_token,
                google_requests.Request(),
                settings.GOOGLE_CLIENT_ID
            )

            email = id_info['email']
            name = id_info.get('name', '')
            google_user_id = id_info['sub']

            user, created = User.objects.get_or_create(
                email=email,
                defaults={
                    'full_name': name,
                    'google_id': google_user_id,
                }
            )

            if not created and not user.google_id:
                user.google_id = google_user_id
                user.save()

            tokens = get_tokens_for_user(user)

            return Response({
                'user': UserSerializer(user, context={'request': request}).data,
                'tokens': tokens,
                'is_new_user': created,
            })

        except ValueError:
            return Response(
                {'error': 'Invalid Google token'},
                status=status.HTTP_400_BAD_REQUEST
            )


# 🟢 LOGOUT
class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get('refresh')

        if not refresh_token:
            return Response({'error': 'Refresh token required'}, status=400)

        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response({'message': 'Logged out successfully'})
        except TokenError:
            return Response({'error': 'Invalid token'}, status=400)


# 🟢 ME
class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(
            UserSerializer(request.user, context={'request': request}).data
        )

    def patch(self, request):
        serializer = UpdateProfileSerializer(
            request.user,
            data=request.data,
            partial=True
        )

        if serializer.is_valid():
            serializer.save()
            return Response(
                UserSerializer(request.user, context={'request': request}).data
            )

        return Response(serializer.errors, status=400)


# 🟢 PROFILE
class UserProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.books_read >= 5 and not request.user.is_avid_reader:
            request.user.is_avid_reader = True
            request.user.save(update_fields=['is_avid_reader'])

        return Response(
            UserProfileSerializer(
                request.user,
                context={'request': request}
            ).data
        )

    def patch(self, request):
        serializer = UpdateProfileSerializer(
            request.user,
            data=request.data,
            partial=True
        )

        if serializer.is_valid():
            serializer.save()
            return Response(
                UserProfileSerializer(
                    request.user,
                    context={'request': request}
                ).data
            )

        return Response(serializer.errors, status=400)


# 🟢 AVATAR UPLOAD
class AvatarUploadView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        file = request.FILES.get('file')

        if not file:
            return Response({'error': 'No file provided'}, status=400)

        user = request.user
        user.avatar = file
        user.save()

        return Response({
            'avatar_url': request.build_absolute_uri(user.avatar.url)
        })


# 🟢 CHANGE PASSWORD
class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(
            data=request.data,
            context={'request': request},
        )

        if not serializer.is_valid():
            return Response(serializer.errors, status=400)

        request.user.set_password(serializer.validated_data['new_password'])
        request.user.save()

        return Response({
            'message': 'Password changed. Please log in again.'
        })


# 🟢 FORGOT PASSWORD
class ForgotPasswordView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ForgotPasswordSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=400)

        email = serializer.validated_data['email'].lower()

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({'message': 'If email exists, code sent'})

        PasswordResetOTP.objects.filter(user=user, is_used=False).delete()

        code = str(random.randint(1000, 9999))
        PasswordResetOTP.objects.create(user=user, code=code)

        send_mail(
            'Reset Code',
            f'Your code: {code}',
            settings.EMAIL_HOST_USER,
            [email],
        )

        return Response({'message': 'If email exists, code sent'})


# 🟢 VERIFY OTP
class VerifyOTPView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = VerifyOTPSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=400)

        email = serializer.validated_data['email']
        code = serializer.validated_data['code']

        try:
            user = User.objects.get(email=email)
            otp = PasswordResetOTP.objects.filter(
                user=user,
                code=code,
                is_used=False
            ).latest('created_at')

            if otp.is_expired():
                return Response({'error': 'Expired'}, status=400)

            return Response({'message': 'Verified'})

        except:
            return Response({'error': 'Invalid'}, status=400)


# 🟢 RESET PASSWORD
class ResetPasswordView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ResetPasswordSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=400)

        email = serializer.validated_data['email']
        code = serializer.validated_data['code']

        try:
            user = User.objects.get(email=email)
            otp = PasswordResetOTP.objects.filter(
                user=user,
                code=code,
                is_used=False
            ).latest('created_at')

            if otp.is_expired():
                return Response({'error': 'Expired'}, status=400)

            user.set_password(serializer.validated_data['new_password'])
            user.save()

            otp.is_used = True
            otp.save()

            return Response({'message': 'Password reset successful'})

        except:
            return Response({'error': 'Invalid'}, status=400)


# 🟢 UPDATE STATS
class UpdateStatsView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        user.books_read += request.data.get('books_read_delta', 0)
        user.total_pages_read += request.data.get('pages_read_delta', 0)

        if user.books_read >= 5:
            user.is_avid_reader = True

        user.save()

        return Response(
            UserProfileSerializer(user, context={'request': request}).data
        )