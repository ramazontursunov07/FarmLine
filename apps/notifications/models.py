from django.conf import settings
from django.db import models
from django.db.models import Q


class Notification(models.Model):
    """Sayt ichidagi bildirishnoma (qo'ng'iroqcha). Har bir foydalanuvchiga alohida yoziladi."""
    KIND_CHOICES = (
        ('event', 'Hodisa'),
        ('calving', "Tug'ish"),
        ('dry_off', 'Quritish'),
        ('rebreed', "Urug'lantirish"),
        ('milk_drop', 'Sut kamayishi'),
        ('debt', 'Qarz'),
        ('withdrawal', 'Ushlab turish muddati'),
        ('vaccination', 'Vaksinatsiya'),
        ('feed', 'Yem'),
        ('spending', 'Chiqim'),
    )
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, default='event')
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    link = models.CharField(max_length=200, blank=True)  # saytdagi yo'l, masalan /farms/3/animals
    # Kunlik eslatma bir kunda bir marta yozilishi uchun (bo'sh bo'lsa, tekshirilmaydi)
    dedupe_key = models.CharField(max_length=120, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']
        indexes = [models.Index(fields=['user', 'is_read'], name='notif_user_read_idx')]
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'dedupe_key'], condition=~Q(dedupe_key=''), name='notification_unique_dedupe'),
        ]

    def __str__(self):
        return f"{self.user_id}: {self.title}"
