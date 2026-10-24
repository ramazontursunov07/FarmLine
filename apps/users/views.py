import hmac
import html
import ipaddress
import logging
from urllib.parse import urlparse

from django.conf import settings
from django.db import transaction
from django.db.models import Count
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from apps.farms import payroll

from .digest_runner import run_digest_in_background
from .models import DigestRun, PasswordResetToken, TelegramLinkToken, User
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

logger = logging.getLogger(__name__)

# Foydalanuvchi bor-yo'qligidan qat'i nazar har doim shu javob qaytariladi
FORGOT_PASSWORD_DETAIL = (
    "Agar akkaunt mavjud va Telegram ulangan bo'lsa, parolni tiklash havolasi botga yuborildi."
)


class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = RegisterSerializer  # serializatsiya classi
    permission_classes = [AllowAny]  # hamma uchun
    authentication_classes = []  # eskirgan token ochiq endpointni 401 bilan to'sib qo'ymasin
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'register'

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)  # ma'lumotni serializatsiya qilamiz.
        serializer.is_valid(raise_exception=True)  # tekshiramiz.
        user = serializer.save()  # saqlaymiz.

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
    throttle_classes = [ScopedRateThrottle]  # ma'lum vaqt ichida nechta so'rov yuborish mumkinligi.
    throttle_scope = 'login'  # bir daqiqada nechta so'rov yuborishi mumkinligi.


class ChangePasswordView(generics.UpdateAPIView):
    queryset = User.objects.all()
    serializer_class = ChangePasswordSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user

    def update(self, request, *args, **kwargs):
        user = self.get_object()  # obyektni olamiz
        serializer = self.get_serializer(data=request.data)  # serializatsiya qilamiz.
        serializer.is_valid(raise_exception=True)  # agarda xato bo'lsa xatoni chiqaramiz.

        old_password = serializer.validated_data['old_password']  # eski password
        new_password = serializer.validated_data['new_password']  # yangi password

        if not user.check_password(old_password):  # eski parolni tekshiramiz.
            return Response({'old_password': "Eski parol noto'g'ri"}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(new_password)  # agarda eski parol to'g'ri bo'lsa unda yangi parolni kodlaymiz.
        user.save()  # undan keyin saqlaymiz.
        return Response({'detail': "Parol muvaffaqiyatli o'zgartirildi"}, status=status.HTTP_200_OK)  # response


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
    throttle_classes = [ScopedRateThrottle]  # necha marta so'rov yuborish mumkinligi
    throttle_scope = 'telegram_link'  # bir daqiqada nechta so'rov yuborish mumkinligi.

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


def _is_local_host(hostname):
    """localhost yoki lokal tarmoq IP'si (192.168.x.x va h.k.) bo'lsa True. Oddiy domen uchun False."""
    if not hostname or hostname == "localhost":
        return True
    try:
        return not ipaddress.ip_address(hostname).is_global
    except ValueError:
        return False


def build_reset_message(reset_link):
    """
    Telegramga yuboriladigan xabar (HTML). Telegram localhost va lokal IP manzillarni havola deb tanimaydi,
    shuning uchun ishlab chiqishda havola bir bosishda nusxalanadigan <code> ko'rinishida yuboriladi.
    Haqiqiy domen bo'lsa, odatiy bosiladigan havola yuboriladi.
    """
    safe_link = html.escape(reset_link)
    if _is_local_host(urlparse(reset_link).hostname):
        link_part = f"Havolani bosib nusxalang va brauzerga qo'ying:\n<code>{safe_link}</code>"
    else:
        link_part = f'<a href="{safe_link}">Parolni tiklash</a>'
    return (
        "FarmLine: parolni tiklash havolasi (15 daqiqa amal qiladi).\n\n"
        f"{link_part}\n\n"
        "Agar buni siz so'ramagan bo'lsangiz, xabarni e'tiborsiz qoldiring."
    )


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
            send_message(user.telegram_chat_id, build_reset_message(reset_link), parse_mode='HTML')

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


class DailyDigestCronView(APIView):
    """
    Tashqi rejalashtiruvchi (masalan, GitHub Actions) kuniga bir marta chaqiradi va kunlik hisobot Telegramga yuboriladi.
    X-Cron-Secret sarlavhasi CRON_SECRET bilan bir xil bo'lishi shart. Kalit sozlanmagan yoki noto'g'ri bo'lsa, 404
    qaytariladi: begonalar bunday manzil borligini ham bilmasin.
    Bir kunda faqat bir marta ishlaydi; qayta yuborish uchun ?force=1.
    """
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'cron'

    def post(self, request):
        secret = settings.CRON_SECRET
        given = request.headers.get('X-Cron-Secret', '')
        if not secret or not hmac.compare_digest(given.encode('utf-8'), secret.encode('utf-8')):
            return Response(status=status.HTTP_404_NOT_FOUND)

        today = timezone.localdate()
        try:
            payroll.post_due(today)  # oy oxirida ishchilar ish haqi chiqimi
        except Exception:
            logger.exception("Ish haqini yozishda xato")
        run, created = DigestRun.objects.get_or_create(date=today)
        if not created and request.query_params.get('force') != '1':
            return Response({'detail': 'Bugungi hisobot allaqachon yuborilgan'}, status=status.HTTP_200_OK)

        run_digest_in_background(today, run.pk)
        return Response({'detail': 'Hisobot yuborilmoqda'}, status=status.HTTP_202_ACCEPTED)
    