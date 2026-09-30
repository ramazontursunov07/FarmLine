from django.db import models
from django.conf import settings


class Transaction(models.Model):
    TRANSACTION_TYPE_CHOICES = (
        ('kirim', 'Kirim'),
        ('chiqim', 'Chiqim'),
    )

    CATEGORY_CHOICES = (
        ('ozuqa', 'Ozuqa'),
        ('dori', 'Dori-darmon'),
        ('sotuv', 'Sotuv'),
        ('ish_haqi', 'Ish haqi'),
        ('kommunal', 'Kommunal xarajat'),
        ('boshqa', 'Boshqa'),
    )

    farm = models.ForeignKey(
        'farms.Farm',
        on_delete=models.CASCADE,
        related_name='transactions'
    )
    animal_group = models.ForeignKey(
        'animals.AnimalGroup',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='transactions'
    )
    transaction_type = models.CharField(max_length=10, choices=TRANSACTION_TYPE_CHOICES)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.TextField(blank=True)
    date = models.DateField()
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='recorded_transactions'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date']
        verbose_name = "Tranzaksiya"
        verbose_name_plural = "Tranzaksiyalar"

    def __str__(self):
        return f"{self.get_transaction_type_display()} - {self.amount} ({self.farm.name})"
