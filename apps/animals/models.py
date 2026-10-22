from django.conf import settings
from django.db import models
from django.utils import timezone


class AnimalType(models.Model):
    """Hayvon turi"""
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
    breed = models.CharField(max_length=100, blank=True)  # nasl
    count = models.PositiveIntegerField(default=0)  # soni
    birth_date = models.DateField(null=True, blank=True)  # tug'ilgan sanasi
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='faol')  # status
    created_at = models.DateTimeField(auto_now_add=True)  # yaratilganligi.
    updated_at = models.DateTimeField(auto_now=True)  # yangilangan sanasi.

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Hayvon guruhi"
        verbose_name_plural = "Hayvon guruhlari"

    def __str__(self):
        return f"{self.animal_type} - {self.count} ta ({self.farm.name})"


# Guruhdagi hayvonlar sonini o'zgartiradigan ish turlari (nechta ekani majburiy)
COUNT_EVENT_TYPES = ('olim', 'tugilish')


class AnimalEvent(models.Model):  # ishlar
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
    # Ixtiyoriy: voqea guruhning bitta aniq hayvoniga tegishli bo'lsa (individual kartochka)
    animal = models.ForeignKey(
        'animals.Animal',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='events'
    )
    event_type = models.CharField(max_length=20, choices=EVENT_TYPE_CHOICES)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='boshlangan')
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    # Nechta hayvonga tegishli. O'lim/tug'ilishda majburiy va guruh sonini o'zgartiradi
    animal_count = models.PositiveIntegerField(null=True, blank=True)
    # Davolashda ishlatilgan dori (ombordan) va "ushlab turish" muddati: shuncha kun sut/go'sht sotib bo'lmaydi
    medicine = models.ForeignKey(
        'inventory.InventoryItem', on_delete=models.SET_NULL, null=True, blank=True, related_name='treatments')
    withdrawal_days = models.PositiveSmallIntegerField(default=0)
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
        end = self.end_date or timezone.now().date()
        return (end - self.start_date).days


class Animal(models.Model):
    """Guruh ichidagi alohida hayvon kartochkasi (masalan, quloq raqami №14 sigir). Ixtiyoriy."""
    SEX_CHOICES = (
        ('urgochi', "Urg'ochi"),
        ('erkak', 'Erkak'),
    )
    STATUS_CHOICES = (
        ('faol', 'Faol'),
        ('sotilgan', 'Sotilgan'),
        ('olgan', "O'lgan"),
    )

    # farm guruhdan olinadi, lekin quloq raqami fermada noyob bo'lishi uchun alohida saqlanadi
    farm = models.ForeignKey('farms.Farm', on_delete=models.CASCADE, related_name='animals')
    group = models.ForeignKey(AnimalGroup, on_delete=models.CASCADE, related_name='animals')
    tag_number = models.CharField(max_length=30)  # quloq raqami / birka
    name = models.CharField(max_length=100, blank=True)  # laqabi
    sex = models.CharField(max_length=10, choices=SEX_CHOICES, default='urgochi')
    birth_date = models.DateField(null=True, blank=True)
    mother = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='calves')
    pregnant_since = models.DateField(null=True, blank=True)  # bug'ozlik boshlangan (urug'lantirilgan) sana
    due_date = models.DateField(null=True, blank=True)  # taxminiy tug'ish sanasi
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='faol')
    notes = models.TextField(blank=True)
    # Qaysi tug'ilish yozuvi bilan birga ochilgan (yozuv o'chirilganda buzoq kartochkasini ham o'chirish uchun)
    birth_event = models.ForeignKey('animals.AnimalEvent', on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='newborns')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['tag_number']
        verbose_name = "Hayvon kartochkasi"
        verbose_name_plural = "Hayvon kartochkalari"
        constraints = [
            models.UniqueConstraint(fields=['farm', 'tag_number'], name='unique_animal_tag_per_farm'),
        ]

    def __str__(self):
        return f"№{self.tag_number} {self.name}".strip()


class WeightRecord(models.Model):
    """Hayvon vazni tarixi (kg)."""
    animal = models.ForeignKey(Animal, on_delete=models.CASCADE, related_name='weights')
    date = models.DateField()
    weight_kg = models.DecimalField(max_digits=7, decimal_places=1)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='recorded_weights'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-id']
        constraints = [
            models.UniqueConstraint(fields=['animal', 'date'], name='unique_weight_per_animal_day'),
        ]

    def __str__(self):
        return f"{self.animal} - {self.weight_kg} kg ({self.date})"


class MilkRecord(models.Model):
    """Sut miqdori (litr). Kuniga bir yoki bir necha marta (ertalab/kechqurun) yozilishi mumkin."""
    SESSION_CHOICES = (
        ('kun', 'Butun kun'),
        ('ertalab', 'Ertalab'),
        ('kechqurun', 'Kechqurun'),
    )

    animal = models.ForeignKey(Animal, on_delete=models.CASCADE, related_name='milk_records')
    date = models.DateField()
    session = models.CharField(max_length=10, choices=SESSION_CHOICES, default='kun')
    liters = models.DecimalField(max_digits=6, decimal_places=1)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='recorded_milk'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-id']
        constraints = [
            models.UniqueConstraint(fields=['animal', 'date', 'session'], name='unique_milk_per_animal_session'),
        ]

    def __str__(self):
        return f"{self.animal} - {self.liters} l ({self.date}, {self.session})"


class MilkSale(models.Model):
    """
    Sotilgan sut (litr). Ombordagi sut kamayadi, puli moliyada "Kirim" bo'lib yoziladi.
    Yozuv ro'yxatdan "o'chirilganda" (is_hidden=True) faqat ko'rinmay qoladi: sut hisobi va balans o'zgarmaydi.
    """
    farm = models.ForeignKey('farms.Farm', on_delete=models.CASCADE, related_name='milk_sales')
    date = models.DateField()
    liters = models.DecimalField(max_digits=8, decimal_places=1)
    price_per_liter = models.DecimalField(max_digits=10, decimal_places=2)
    amount = models.DecimalField(max_digits=12, decimal_places=2)  # liters * price_per_liter
    note = models.CharField(max_length=200, blank=True)  # kimga sotildi va h.k.
    finance_transaction = models.OneToOneField(
        'finance.Transaction', on_delete=models.SET_NULL, null=True, blank=True, related_name='milk_sale'
    )
    # Nasiyaga sotilgan bo'lsa: ochilgan qarz (pul to'langan sari balansga tushadi)
    debt = models.OneToOneField(
        'debts.Debt', on_delete=models.SET_NULL, null=True, blank=True, related_name='milk_sale')
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='recorded_milk_sales'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    # Tarixdan o'chirilgan: ro'yxatda ko'rinmaydi, lekin sotilgan sut hisobida va moliyadagi kirimda qoladi
    is_hidden = models.BooleanField(default=False)

    class Meta:
        ordering = ['-date', '-id']
        verbose_name = "Sotilgan sut"
        verbose_name_plural = "Sotilgan sutlar"

    def __str__(self):
        return f"{self.farm}: {self.liters} l ({self.date})"
