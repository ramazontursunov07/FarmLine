from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

# AI taklif qilgan amal shu vaqt ichida tasdiqlanmasa, kuchini yo'qotadi
PENDING_TTL = timedelta(minutes=30)


class PendingAction(models.Model):
    """AI taklif qilgan, foydalanuvchi tasdiqlashi kutilayotgan amallar (ombor, kirim-chiqim).

    AI hech narsani o'zi bajarmaydi: avval shu yozuv yaratiladi, foydalanuvchi "Tasdiqlash"ni bosgach
    tizim amalni oddiy API bilan bir xil qoidalar (ruxsat, zaxira tekshiruvi, Telegram xabari) asosida bajaradi.
    Yozuvlar tarix sifatida qoladi: AI nimani taklif qilgani va nima bajarilgani ko'rinib turadi.
    """
    STATUS_CHOICES = (
        ('kutilmoqda', 'Kutilmoqda'),
        ('bajarildi', 'Bajarildi'),
        ('bekor', 'Bekor qilindi'),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='pending_ai_actions',
    )
    # Tekshirilgan amallar ro'yxati: [{type, data, title, details}, ...]
    actions = models.JSONField(default=list)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='kutilmoqda')
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "AI amali"
        verbose_name_plural = "AI amallari"

    def __str__(self):
        return f"{self.user} - {self.get_status_display()} ({self.created_at:%d.%m.%Y %H:%M})"

    @property
    def expires_at(self):
        return self.created_at + PENDING_TTL

    @property
    def is_expired(self):
        return timezone.now() > self.expires_at
    