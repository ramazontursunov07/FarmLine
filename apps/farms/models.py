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
    name = models.CharField(max_length=255)  # ferma nomi
    location = models.CharField(max_length=255)  # ferma lokatsiyasi
    latitude = models.FloatField(null=True, blank=True, editable=False)  # ob-havo uchun (manzildan avtomatik topiladi)
    longitude = models.FloatField(null=True, blank=True, editable=False)
    farm_type = models.CharField(max_length=20, choices=FARM_TYPE_CHOICES)  # qanaqa yo'nalishdagi ferma.
    created_at = models.DateTimeField(auto_now_add=True)  # yaratilgan sanasi
    updated_at = models.DateTimeField(auto_now=True)  # yangilangan sanasi

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Xo'jalik"
        verbose_name_plural = "Xo'jaliklar"

    def __str__(self):
        return f"{self.name} ({self.owner.username})"


class Worker(models.Model):  # ishchi
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='worker_profiles'
    )
    farm = models.ForeignKey(  # qaysi fermada ishchi bo'lib ishlashi.
        Farm,
        on_delete=models.CASCADE,
        related_name='workers'
    )
    KIND_CHOICES = (
        ('ishchi', 'Ishchi'),
        ('veterinar', 'Veterinar'),
    )
    # Veterinar faqat davolash va vaksinatsiya yozuvlarini ko'radi va yozadi; moliya, sut, ombor unga yopiq.
    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default='ishchi')
    can_view_finance = models.BooleanField(default=False)  # kirim-chiqimlarni ko'rishga ruxsat bormi yokida yo'qmi.
    # Oylik (so'm). 0 bo'lsa, oy oxirida avtomatik chiqim yozilmaydi.
    monthly_salary = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    # Oylik qaysi sanadan hisoblana boshlaydi (oylik birinchi marta kiritilganda o'zi qo'yiladi)
    salary_from = models.DateField(null=True, blank=True)
    joined_at = models.DateTimeField(auto_now_add=True)  # yaratilgan sanasi.

    class Meta:
        ordering = ['-joined_at']
        verbose_name = "Ishchi"
        verbose_name_plural = "Ishchilar"
        unique_together = ('user', 'farm')  # har bir ishchi bitta fermada ishlaydi.

    def __str__(self):
        return f"{self.user.username} - {self.farm.name}"


class SalaryPayment(models.Model):
    """Ishchining bir oylik ish haqi moliyaga chiqim qilib yozilgani. (ishchi, oy) bo'yicha noyob: ikki marta yozilmaydi."""
    worker = models.ForeignKey(Worker, on_delete=models.CASCADE, related_name='salary_payments')
    month = models.DateField()  # oyning 1-kuni
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    # Chiqim o'chirilsa ham yozuv qoladi: o'sha oy uchun qayta yozilmaydi
    transaction = models.ForeignKey('finance.Transaction', on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='salary_payments')
    # Kelmagan kunlar va ushlab qolingan summa (amount — ushlab qolingandan keyingi, ya'ni to'lanadigan summa)
    absent_days = models.PositiveSmallIntegerField(default=0)
    deduction = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-month']
        verbose_name = "Ish haqi to'lovi"
        verbose_name_plural = "Ish haqi to'lovlari"
        constraints = [
            models.UniqueConstraint(fields=['worker', 'month'], name='unique_salary_per_worker_month'),
        ]

    def __str__(self):
        return f"{self.worker} {self.month:%Y-%m}: {self.amount}"


class Attendance(models.Model):
    """
    Ishchi davomati. Faqat kelmagan / ruxsatli kunlar yoziladi: yozuv bo'lmagan kun "keldi" hisoblanadi.
    'kelmadi' kunlari oylikdan ushlab qolinadi, 'ruxsat' (kasallik, ta'til) — ushlanmaydi.
    """
    STATUS_CHOICES = (
        ('kelmadi', 'Kelmadi'),
        ('ruxsat', 'Ruxsat bilan'),
    )
    worker = models.ForeignKey(Worker, on_delete=models.CASCADE, related_name='attendance')
    date = models.DateField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)
    note = models.CharField(max_length=200, blank=True)
    marked_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date']
        verbose_name = "Davomat"
        verbose_name_plural = "Davomat"
        constraints = [
            models.UniqueConstraint(fields=['worker', 'date'], name='unique_attendance_per_worker_day'),
        ]

    def __str__(self):
        return f"{self.worker} {self.date}: {self.status}"
    