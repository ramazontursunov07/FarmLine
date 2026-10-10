import secrets
import uuid
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class User(AbstractUser):
    ROLE_CHOICES = (
        ('admin', 'Admin'),
        ('fermer', 'Fermer'),
        ('ishchi', 'Ishchi'),
    )
    role = models.CharField(choices=ROLE_CHOICES, max_length=10, default='fermer')  # foydalanuvchi roli
    phone_number = models.CharField(max_length=20, blank=True, null=True)  # telefon raqami
    telegram_chat_id = models.CharField(max_length=50, blank=True, null=True)  # ulangan Telegram chat id

    def __str__(self):
        return self.username


class PasswordResetToken(models.Model):
    """Parolni tiklash uchun bir martalik token. Faqat foydalanuvchining ulangan Telegramiga yuboriladi."""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='reset_tokens'
    )
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Parol tiklash tokeni"
        verbose_name_plural = "Parol tiklash tokenlari"

    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(minutes=15)
        super().save(*args, **kwargs)

    def is_valid(self):
        return not self.is_used and timezone.now() < self.expires_at

    def __str__(self):
        return f"{self.user.username} - {self.token} ({'ishlatilgan' if self.is_used else 'faol'})"


class TelegramLinkToken(models.Model):
    """
    Akkauntni Telegram bilan ulash uchun qisqa muddatli bir martalik kod.
    Kodni faqat tizimga kirgan foydalanuvchi oladi, shuning uchun
    Telegram chat faqat akkaunt egasiga ulanadi.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='telegram_link_tokens'
    )
    code = models.CharField(max_length=64, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Telegram ulash kodi"
        verbose_name_plural = "Telegram ulash kodlari"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = secrets.token_urlsafe(24)  # Telegram deep-link uchun mos belgilar
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(minutes=10)
        super().save(*args, **kwargs)

    def is_valid(self):
        return not self.is_used and timezone.now() < self.expires_at

    def __str__(self):
        return f"{self.user.username} - Telegram ulash ({'ishlatilgan' if self.is_used else 'faol'})"
    