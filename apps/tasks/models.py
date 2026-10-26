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


class RecurringTask(models.Model):
    """
    Takrorlanuvchi vazifa (masalan, har yili vaksinatsiya, har oy mollarni tortish).
    `next_due` kelganda (yoki `lead_days` kun oldin) oddiy `Task` o'zi yaratiladi va ishchiga Telegramdan xabar boradi.
    """
    FREQUENCY_CHOICES = (
        ('kunlik', 'Har kuni'),
        ('haftalik', 'Har hafta'),
        ('oylik', 'Har oy'),
        ('yillik', 'Har yili'),
    )

    farm = models.ForeignKey('farms.Farm', on_delete=models.CASCADE, related_name='recurring_tasks')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    # null bo'lsa, vazifa fermaning barcha ishchilari uchun
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='recurring_assigned',
    )
    priority = models.CharField(max_length=20, choices=Task.PRIORITY_CHOICES, default='oddiy')
    frequency = models.CharField(max_length=10, choices=FREQUENCY_CHOICES)
    interval = models.PositiveSmallIntegerField(default=1)  # har necha hafta/oy/yilda (1 = har safar)
    next_due = models.DateField()  # keyingi vazifa muddati
    anchor_day = models.PositiveSmallIntegerField(
        default=1)  # oy/yil uchun: oyning qaysi kuni (31 -> qisqa oyda oxirgi kun)
    lead_days = models.PositiveSmallIntegerField(default=0)  # muddatdan necha kun oldin vazifa yaratilsin
    is_active = models.BooleanField(default=True)
    last_created_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='created_recurring_tasks',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['next_due', 'id']
        verbose_name = "Takrorlanuvchi vazifa"
        verbose_name_plural = "Takrorlanuvchi vazifalar"

    def __str__(self):
        return f"{self.title} ({self.get_frequency_display()})"
    