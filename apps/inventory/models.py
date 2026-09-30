from django.db import models
from django.conf import settings


class InventoryItem(models.Model):
    ITEM_TYPE_CHOICES = (
        ('ozuqa', 'Ozuqa'),
        ('dori', 'Dori-darmon'),
        ('boshqa', 'Boshqa'),
    )

    farm = models.ForeignKey(
        'farms.Farm',
        on_delete=models.CASCADE,
        related_name='inventory_items'
    )
    item_name = models.CharField(max_length=255)
    item_type = models.CharField(max_length=20, choices=ITEM_TYPE_CHOICES)
    quantity = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    unit = models.CharField(max_length=20)
    low_stock_threshold = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['item_name']
        verbose_name = "Ombor mahsuloti"
        verbose_name_plural = "Ombor mahsulotlari"

    def __str__(self):
        return f"{self.item_name} ({self.quantity} {self.unit})"

    @property
    def is_low_stock(self):
        """Zaxiradagi mahsulot kam qolganda ogohlantirish."""
        return self.quantity <= self.low_stock_threshold


class InventoryTransaction(models.Model):
    TRANSACTION_TYPE_CHOICES = (
        ('kirim', 'Kirim'),
        ('sarf', 'Sarf'),
    )

    inventory_item = models.ForeignKey(
        InventoryItem,
        on_delete=models.CASCADE,
        related_name='transactions'
    )
    transaction_type = models.CharField(max_length=10, choices=TRANSACTION_TYPE_CHOICES)
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    date = models.DateField()
    note = models.TextField(blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='recorded_inventory_transactions'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date']
        verbose_name = "Ombor harakati"
        verbose_name_plural = "Ombor harakatlari"

    def __str__(self):
        return f"{self.get_transaction_type_display()} - {self.quantity} ({self.inventory_item.item_name})"
