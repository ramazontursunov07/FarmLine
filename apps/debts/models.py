from django.conf import settings
from django.db import models


class Party(models.Model):
    """
    Qarz bo'yicha tomon.
    mijoz       -- sutni (yoki boshqa mahsulotni) nasiyaga olgan odam: u fermerga qarzdor.
    taminotchi  -- yemni (yoki boshqa narsani) nasiyaga bergan odam: fermer unga qarzdor.
    """
    KIND_CHOICES = (
        ('mijoz', 'Mijoz'),
        ('taminotchi', "Yetkazib beruvchi"),
    )

    farm = models.ForeignKey('farms.Farm', on_delete=models.CASCADE, related_name='debt_parties')
    kind = models.CharField(max_length=12, choices=KIND_CHOICES, default='mijoz')
    name = models.CharField(max_length=120)
    phone = models.CharField(max_length=30, blank=True)
    note = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        verbose_name = "Qarz tomoni"
        verbose_name_plural = "Qarz tomonlari"
        constraints = [
            models.UniqueConstraint(fields=['farm', 'kind', 'name'], name='unique_debt_party_per_farm_kind'),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_kind_display()})"


class Debt(models.Model):
    """Bitta nasiya: qancha, qachon berilgan, qachongacha to'lanishi kerak."""
    farm = models.ForeignKey('farms.Farm', on_delete=models.CASCADE, related_name='debts')
    party = models.ForeignKey(Party, on_delete=models.CASCADE, related_name='debts')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    date = models.DateField()
    due_date = models.DateField(null=True, blank=True)  # to'lash muddati (bo'sh bo'lsa muddatsiz)
    description = models.CharField(max_length=200, blank=True)  # masalan: "120 litr sut"
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='recorded_debts'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-id']
        verbose_name = "Qarz"
        verbose_name_plural = "Qarzlar"

    def __str__(self):
        return f"{self.party}: {self.amount} ({self.date})"


class DebtPayment(models.Model):
    """Qarzdan to'langan qism (bir qarzga bir necha marta to'lash mumkin)."""
    debt = models.ForeignKey(Debt, on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    date = models.DateField()
    note = models.CharField(max_length=200, blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='recorded_debt_payments'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-id']

    def __str__(self):
        return f"{self.debt_id}: {self.amount} ({self.date})"
    