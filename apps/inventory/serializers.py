from rest_framework import serializers
from .models import InventoryItem, InventoryTransaction


class InventoryItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = InventoryItem
        fields = ['id', 'farm', 'item_name', 'quantity', 'unit', 'low_stock_threshold', 'updated_at', 'created_at']


class InventoryTransactionSerializer(serializers.ModelSerializer):
    inventory_name = serializers.CharField(source='inventory_item.item_name', read_only=True)

    class Meta:
        model = InventoryTransaction
        fields = ['id', 'inventory_item', 'inventory_name', 'transaction_type',
                  'quantity', 'date', 'note', 'recorded_by', 'created_at']
        read_only_fields = ['recorded_by']
