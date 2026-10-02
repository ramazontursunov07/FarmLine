from rest_framework import serializers
from .models import Transaction


class TransactionSerializer(serializers.ModelSerializer):
    farm_name = serializers.CharField(source='farm.name', read_only=True)
    animal_group_info = serializers.SerializerMethodField()

    class Meta:
        model = Transaction
        fields = ['id', 'farm', 'farm_name', 'animal_group_info', 'animal_group', 'transaction_type', 'category',
                  'amount',
                  'description', 'date',
                  'recorded_by', 'created_at']

        read_only_fields = ['recorded_by']

    def get_animal_group_info(self, obj):
        if obj.animal_group:
            return str(obj.animal_group)
        return None
