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
    name = models.CharField(max_length=255)
    location = models.CharField(max_length=255)
    farm_type = models.CharField(max_length=20, choices=FARM_TYPE_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Xo'jalik"
        verbose_name_plural = "Xo'jaliklar"

    def __str__(self):
        return f"{self.name} ({self.owner.username})"


class Worker(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='worker_profiles'
    )
    farm = models.ForeignKey(
        Farm,
        on_delete=models.CASCADE,
        related_name='workers'
    )
    can_view_finance = models.BooleanField(default=False)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-joined_at']
        verbose_name = "Ishchi"
        verbose_name_plural = "Ishchilar"
        unique_together = ('user', 'farm')

    def __str__(self):
        return f"{self.user.username} - {self.farm.name}"
