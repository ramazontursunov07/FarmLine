from rest_framework import serializers

from .models import InventoryItem, InventoryTransaction


class InventoryItemSerializer(serializers.ModelSerializer):
    farm_name = serializers.CharField(source='farm.name', read_only=True)
    item_type_display = serializers.CharField(source='get_item_type_display', read_only=True)
    is_low_stock = serializers.ReadOnlyField()

    class Meta:
        model = InventoryItem
        fields = [
            'id', 'farm', 'farm_name', 'item_name', 'item_type', 'item_type_display',
            'quantity', 'unit', 'low_stock_threshold', 'is_low_stock',
            'updated_at', 'created_at',
        ]

    def validate_quantity(self, value):
        if value < 0:
            raise serializers.ValidationError("Miqdor manfiy bo'lishi mumkin emas")
        return value

    def validate_low_stock_threshold(self, value):
        if value < 0:
            raise serializers.ValidationError("Chegara manfiy bo'lishi mumkin emas")
        return value

    def update(self, instance, validated_data):
        validated_data.pop('farm', None)  # mahsulotni boshqa fermaga ko'chirib bo'lmaydi
        # Miqdor faqat kirim/sarf yozuvlari orqali o'zgaradi
        if 'quantity' in validated_data and validated_data['quantity'] != instance.quantity:
            raise serializers.ValidationError(
                {'quantity': "Miqdorni to'g'ridan-to'g'ri o'zgartirib bo'lmaydi. Kirim yoki sarf yozing."}
            )
        validated_data.pop('quantity', None)
        return super().update(instance, validated_data)


class InventoryTransactionSerializer(serializers.ModelSerializer):
    inventory_name = serializers.CharField(source='inventory_item.item_name', read_only=True)
    inventory_unit = serializers.CharField(source='inventory_item.unit', read_only=True)
    farm = serializers.IntegerField(source='inventory_item.farm_id', read_only=True)
    transaction_type_display = serializers.CharField(source='get_transaction_type_display', read_only=True)
    recorded_by_name = serializers.SerializerMethodField()

    class Meta:
        model = InventoryTransaction
        fields = [
            'id', 'farm', 'inventory_item', 'inventory_name', 'inventory_unit',
            'transaction_type', 'transaction_type_display', 'quantity', 'date', 'note',
            'recorded_by', 'recorded_by_name', 'created_at',
        ]
        read_only_fields = ['recorded_by']

    def get_recorded_by_name(self, obj):
        user = obj.recorded_by
        if not user:
            return None
        return user.get_full_name() or user.username

    def validate_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError("Miqdor noldan katta bo'lishi kerak")
        return value
