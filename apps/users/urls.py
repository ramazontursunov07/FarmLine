from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    AdminUserListView,
    ChangePasswordView,
    CustomTokenObtainPairView,
    DailyDigestCronView,
    LogoutView,
    WorkReportCronView,
    ForgotPasswordView,
    RegisterView,
    ResetPasswordView,
    TelegramLinkView,
    UserUpdateView,
)

urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', CustomTokenObtainPairView.as_view(), name='login'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('change-password/', ChangePasswordView.as_view(), name='change_password'),
    path('profile/', UserUpdateView.as_view(), name='profile'),
    path('telegram/link/', TelegramLinkView.as_view(), name='telegram_link'),
    path('forgot-password/', ForgotPasswordView.as_view(), name='forgot_password'),
    path('reset-password/', ResetPasswordView.as_view(), name='reset_password'),
    path('list/', AdminUserListView.as_view(), name='admin_user_list'),
    path('cron/daily-digest/', DailyDigestCronView.as_view(), name='cron_daily_digest'),
    path('cron/work-report/', WorkReportCronView.as_view(), name='cron_work_report'),
]
