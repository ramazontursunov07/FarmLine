from rest_framework import serializers
from .models import Transaction


class TransactionSerializer(serializers.ModelSerializer):
    farm_name = serializers.CharField(source="farm.name", read_only=True)
    animal_group_info = serializers.SerializerMethodField()
    recorded_by_username = serializers.CharField(source="recorded_by.username", read_only=True)

    class Meta:
        model = Transaction
        fields = ["id", "farm", "farm_name", "animal_group_info", "animal_group", "transaction_type", "category",
                  "amount", "description", "date",
                  "recorded_by", "recorded_by_username", "created_at"]

        read_only_fields = ["recorded_by"]

    def get_animal_group_info(self, obj):
        if obj.animal_group:
            return str(obj.animal_group)
        return None

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Summa 0 dan katta bo'lishi kerak")
        return value

    def validate(self, attrs):
        farm = attrs.get("farm") or getattr(self.instance, "farm", None)
        group = attrs.get("animal_group", getattr(self.instance, "animal_group", None))
        if group and farm and group.farm_id != farm.id:
            raise serializers.ValidationError(
                {"animal_group": "Bu hayvon guruhi tanlangan fermaga tegishli emas"}
            )
        return attrs
