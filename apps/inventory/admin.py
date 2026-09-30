from django.contrib import admin
from .models import InventoryItem, InventoryTransaction

admin.site.register(InventoryItem)
admin.site.register(InventoryTransaction)
