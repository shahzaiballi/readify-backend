from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from . import views

urlpatterns = [
    # Registration & Login
    path('register/', views.RegisterView.as_view(), name='register'),
    path('login/', views.LoginView.as_view(), name='login'),
    path('google/', views.GoogleAuthView.as_view(), name='google-auth'),
    path('logout/', views.LogoutView.as_view(), name='logout'),

    # Token management
    path('token/refresh/', TokenRefreshView.as_view(), name='token-refresh'),

    # Basic identity
    path('me/', views.MeView.as_view(), name='me'),

    # Full profile with stats + achievements (this is what Flutter calls)
    path('profile/', views.UserProfileView.as_view(), name='profile'),

    # Password management
    path('change-password/', views.ChangePasswordView.as_view(), name='change-password'),
    path('forgot-password/', views.ForgotPasswordView.as_view(), name='forgot-password'),
    path('verify-otp/', views.VerifyOTPView.as_view(), name='verify-otp'),
    path('reset-password/', views.ResetPasswordView.as_view(), name='reset-password'),

    # Stats update
    path('stats/update/', views.UpdateStatsView.as_view(), name='update-stats'),
]