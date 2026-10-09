from rest_framework import serializers
from .models import Transaction


class TransactionSerializer(serializers.ModelSerializer):
    farm_name = serializers.CharField(source="farm.name", read_only=True)
    animal_group_info = serializers.SerializerMethodField()
    animal_group_label = serializers.SerializerMethodField()
    animal_count = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    recorded_by_username = serializers.CharField(source="recorded_by.username", read_only=True)

    class Meta:
        model = Transaction
        fields = ["id", "farm", "farm_name", "animal_group_info", "animal_group_label", "animal_group", "animal_count",
                  "transaction_type", "category", "amount", "description", "date",
                  "recorded_by", "recorded_by_username", "created_at"]

        read_only_fields = ["recorded_by"]

    def get_animal_group_info(self, obj):
        if obj.animal_group:
            return str(obj.animal_group)
        return None

    def get_animal_group_label(self, obj):
        group = obj.animal_group
        if not group:
            return None
        return f"{group.animal_type.name} ({group.breed})" if group.breed else group.animal_type.name

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

        def pick(name):
            return attrs[name] if name in attrs else getattr(self.instance, name, None)

        count = pick("animal_count")
        if count:
            if not group:
                raise serializers.ValidationError({"animal_group": "Sotilgan hayvonlar uchun hayvon guruhini tanlang"})
            if pick("transaction_type") != "kirim" or pick("category") != "sotuv":
                raise serializers.ValidationError(
                    {"animal_count": "Hayvon sonini faqat \"Kirim\" va \"Sotuv\" yozuvida ko'rsatish mumkin"}
                )

        # Hayvon soni bog'langan yozuvni keyin o'zgartirib bo'lmaydi (guruh soni buzilib qolmasligi uchun)
        if self.instance:
            if "animal_count" in attrs and attrs["animal_count"] != self.instance.animal_count:
                raise serializers.ValidationError(
                    {"animal_count": "Hayvon sonini keyin o'zgartirib bo'lmaydi. Yozuvni o'chirib, qaytadan kiriting."}
                )
            if self.instance.animal_count:
                for name in ("animal_group", "transaction_type", "category", "farm"):
                    if name in attrs and attrs[name] != getattr(self.instance, name):
                        raise serializers.ValidationError(
                            {
                                name: "Hayvonlar soni bog'langan yozuvda buni o'zgartirib bo'lmaydi. Yozuvni o'chirib, qaytadan kiriting."}
                        )
        return attrs
