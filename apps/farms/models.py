from django.db import models
from django.conf import settings


class Farm(models.Model):
    FARM_TYPE_CHOICES = (
        ('chorvachilik', 'Chorvachilik'),
        ('parrandachilik', 'Parrandachilik'),
        ('aralash', 'Aralash'),
    )

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='owned_farms'
    )
    name = models.CharField(max_length=255) #ferma nomi
    location = models.CharField(max_length=255) #ferma lokatsiyasi
    farm_type = models.CharField(max_length=20, choices=FARM_TYPE_CHOICES) #qanaqa yo'nalishdagi ferma.
    created_at = models.DateTimeField(auto_now_add=True) #yaratilgan sanasi
    updated_at = models.DateTimeField(auto_now=True) #yangilangan sanasi

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Xo'jalik"
        verbose_name_plural = "Xo'jaliklar"

    def __str__(self):
        return f"{self.name} ({self.owner.username})"


class Worker(models.Model): #ishchi
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='worker_profiles'
    )
    farm = models.ForeignKey( #qaysi fermada ishchi bo'lib ishlashi.
        Farm,
        on_delete=models.CASCADE,
        related_name='workers'
    )
    can_view_finance = models.BooleanField(default=False) #kirim-chiqimlarni ko'rishga ruxsat bormi yokida yo'qmi.
    joined_at = models.DateTimeField(auto_now_add=True) #yaratilgan sanasi.

    class Meta:
        ordering = ['-joined_at']
        verbose_name = "Ishchi"
        verbose_name_plural = "Ishchilar"
        unique_together = ('user', 'farm')  #har bir ishchi bitta fermada ishlaydi.

    def __str__(self):
        return f"{self.user.username} - {self.farm.name}"
