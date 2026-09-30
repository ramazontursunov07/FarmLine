from django.conf import settings
from django.db import models


class AnimalType(models.Model):
    name = models.CharField(max_length=50, unique=True)

    class Meta:
        verbose_name = "Hayvon turi"
        verbose_name_plural = "Hayvon turlari"

    def __str__(self):
        return self.name


class AnimalGroup(models.Model):
    STATUS_CHOICES = (
        ('faol', 'Faol'),
        ('sotilgan', 'Sotilgan'),
        ('olgan', "O'lgan"),
        ('yoqolgan', "Yo'qolgan"),
    )

    farm = models.ForeignKey(
        'farms.Farm',
        on_delete=models.CASCADE,
        related_name='animal_groups'
    )
    animal_type = models.ForeignKey(
        AnimalType,
        on_delete=models.PROTECT,
        related_name='groups'
    )
    breed = models.CharField(max_length=100, blank=True)
    count = models.PositiveIntegerField(default=0)
    birth_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='faol')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Hayvon guruhi"
        verbose_name_plural = "Hayvon guruhlari"

    def __str__(self):
        return f"{self.animal_type} - {self.count} ta ({self.farm.name})"


class AnimalEvent(models.Model):
    EVENT_TYPE_CHOICES = (
        ('kasallik', 'Kasallik'),
        ('davolash', 'Davolash'),
        ('vaksinatsiya', 'Vaksinatsiya'),
        ('tugilish', "Tug'ilish"),
        ('olim', "O'lim"),
        ('vazn_olchash', "Vazn o'lchash"),
    )

    STATUS_CHOICES = (
        ('boshlangan', 'Boshlangan'),
        ('davom_etmoqda', 'Davom etmoqda'),
        ('yakunlangan', 'Yakunlangan'),
    )

    animal_group = models.ForeignKey(
        'animals.AnimalGroup',
        on_delete=models.CASCADE,
        related_name='events'
    )
    event_type = models.CharField(max_length=20, choices=EVENT_TYPE_CHOICES)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='boshlangan')
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='recorded_events'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-start_date']

    def __str__(self):
        return f"{self.get_event_type_display()} - {self.animal_group} ({self.start_date})"

    @property
    def days_since_start(self):
        """Voqea boshlangandan beri necha kun o'tgani (masalan davolanish davomiyligi)"""
        from django.utils import timezone
        end = self.end_date or timezone.now().date()
        return (end - self.start_date).days
