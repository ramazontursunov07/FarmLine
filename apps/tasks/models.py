from django.conf import settings
from django.db import models


class Task(models.Model):
    """Fermer ishchiga beradigan vazifa."""
    PRIORITY_CHOICES = (
        ('oddiy', 'Oddiy'),
        ('muhim', 'Muhim'),
        ('shoshilinch', 'Shoshilinch'),
    )
    STATUS_CHOICES = (
        ('yangi', 'Yangi'),
        ('jarayonda', 'Jarayonda'),
        ('bajarildi', 'Bajarildi'),
    )

    farm = models.ForeignKey('farms.Farm', on_delete=models.CASCADE, related_name='tasks')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    # null bo'lsa, vazifa fermaning barcha ishchilari uchun
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='assigned_tasks',
    )
    due_date = models.DateField(null=True, blank=True)
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='oddiy')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='yangi')
    result_note = models.TextField(blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, related_name='created_tasks',
    )
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='completed_tasks',
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Vazifa"
        verbose_name_plural = "Vazifalar"

    def __str__(self):
        return f"{self.title} ({self.farm.name})"
