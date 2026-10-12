from django.conf import settings
from django.db import models


class IdempotencyRecord(models.Model):
    """
    Bajarilgan "yaratish" so'rovi natijasi. Mijoz xuddi shu so'rovni (Idempotency-Key bilan) qayta yuborsa,
    yangi yozuv yaratilmaydi, saqlangan javob qaytariladi. Internet uzilib-ulanganda yozuv ikki marta
    qo'shilib qolmasligi uchun kerak.
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='idempotency_records')
    key = models.CharField(max_length=64)
    path = models.CharField(max_length=255)
    status_code = models.PositiveSmallIntegerField(null=True)
    response_body = models.JSONField(null=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'key'], name='unique_idempotency_key_per_user'),
        ]

    def __str__(self):
        return f"{self.user_id}:{self.key}"
    