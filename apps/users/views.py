from django.conf import settings
from django.db import transaction
from django.db.models import Count
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import PasswordResetToken, TelegramLinkToken, User
from .permissions import IsAppAdmin
from .serializers import (
    AdminUserListSerializer,
    ChangePasswordSerializer,
    CustomTokenObtainPairSerializer,
    ForgotPasswordSerializer,
    RegisterSerializer,
    ResetPasswordSerializer,
    UserUpdateSerializer,
)
from .telegram import build_bot_link, send_message

# Foydalanuvchi bor-yo'qligidan qat'i nazar har doim shu javob qaytariladi
FORGOT_PASSWORD_DETAIL = (
    "Agar akkaunt mavjud va Telegram ulangan bo'lsa, parolni tiklash havolasi botga yuborildi."
)


class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]
    authentication_classes = []  # eskirgan token ochiq endpointni 401 bilan to'sib qo'ymasin
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'register'

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        refresh = RefreshToken.for_user(user)

        return Response({
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'role': user.role
            },
            'access': str(refresh.access_token),
            'refresh': str(refresh)
        }, status=status.HTTP_201_CREATED)


class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'login'


class ChangePasswordView(generics.UpdateAPIView):
    queryset = User.objects.all()
    serializer_class = ChangePasswordSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user

    def update(self, request, *args, **kwargs):
        user = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        old_password = serializer.validated_data['old_password']
        new_password = serializer.validated_data['new_password']

        if not user.check_password(old_password):
            return Response({'old_password': "Eski parol noto'g'ri"}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(new_password)
        user.save()
        return Response({'detail': "Parol muvaffaqiyatli o'zgartirildi"}, status=status.HTTP_200_OK)


class UserUpdateView(generics.RetrieveUpdateAPIView):
    queryset = User.objects.all()
    serializer_class = UserUpdateSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user


class TelegramLinkView(APIView):
    """
    POST   - Telegramni ulash uchun bir martalik havola yaratadi (faqat tizimga kirgan foydalanuvchi).
    DELETE - Telegram ulanishini olib tashlaydi.
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'telegram_link'

    def post(self, request):
        # Eski ishlatilmagan kodlar bekor qilinadi
        TelegramLinkToken.objects.filter(user=request.user, is_used=False).update(is_used=True)
        link_token = TelegramLinkToken.objects.create(user=request.user)
        return Response({
            'telegram_link': build_bot_link(link_token.code),
            'expires_in_minutes': 10,
        }, status=status.HTTP_201_CREATED)

    def delete(self, request):
        request.user.telegram_chat_id = None
        request.user.save(update_fields=['telegram_chat_id'])
        return Response(status=status.HTTP_204_NO_CONTENT)


class ForgotPasswordView(APIView):
    """
    Parolni unutgan foydalanuvchi uchun. Token API javobida HECH QACHON qaytarilmaydi:
    tiklash havolasi faqat akkauntga oldindan ulangan Telegramga yuboriladi.
    Javob foydalanuvchi mavjud yoki mavjud emasligidan qat'i nazar bir xil.
    """
    permission_classes = [AllowAny]
    authentication_classes = []  # eskirgan token ochiq endpointni 401 bilan to'sib qo'ymasin
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'forgot_password'

    def post(self, request):
        serializer = ForgotPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = User.objects.filter(username=serializer.validated_data['username'], is_active=True).first()

        if user and user.telegram_chat_id:
            # Eski faol tokenlar bekor qilinadi, faqat eng yangisi ishlaydi
            PasswordResetToken.objects.filter(user=user, is_used=False).update(is_used=True)
            reset_token = PasswordResetToken.objects.create(user=user)
            reset_link = f"{settings.FRONTEND_URL}/reset-password?token={reset_token.token}"
            send_message(
                user.telegram_chat_id,
                f"FarmLine: parolni tiklash havolasi (15 daqiqa amal qiladi):\n{reset_link}\n\n"
                f"Agar buni siz so'ramagan bo'lsangiz, xabarni e'tiborsiz qoldiring.",
            )

        return Response({'detail': FORGOT_PASSWORD_DETAIL}, status=status.HTTP_200_OK)


class ResetPasswordView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []  # eskirgan token ochiq endpointni 401 bilan to'sib qo'ymasin
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'reset_password'

    def post(self, request):
        serializer = ResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        token_value = serializer.validated_data['token']
        new_password = serializer.validated_data['new_password']

        with transaction.atomic():
            reset_token = (
                PasswordResetToken.objects.select_for_update()
                .select_related('user')
                .filter(token=token_value)
                .first()
            )
            # Topilmadi / muddati tugagan / ishlatilgan: hammasi uchun bitta xabar
            if not reset_token or not reset_token.is_valid():
                return Response({'token': "Havola noto'g'ri yoki muddati tugagan"},
                                status=status.HTTP_400_BAD_REQUEST)

            user = reset_token.user
            user.set_password(new_password)
            user.save(update_fields=['password'])

            # Shu foydalanuvchining barcha faol tokenlari yopiladi
            PasswordResetToken.objects.filter(user=user, is_used=False).update(is_used=True)

        return Response({'detail': 'Parol muvaffaqiyatli yangilandi'}, status=status.HTTP_200_OK)


class AdminUserListView(generics.ListAPIView):
    """Admin uchun foydalanuvchilar ro'yxati. ?role=fermer bilan filtrlash mumkin."""
    serializer_class = AdminUserListSerializer
    permission_classes = [IsAppAdmin]

    def get_queryset(self):
        qs = User.objects.annotate(
            farms_count=Count('owned_farms', distinct=True)
        ).order_by('-date_joined')
        role = self.request.query_params.get('role')
        if role:
            qs = qs.filter(role=role)
        return qs
