from django.utils import timezone
from rest_framework import serializers

from .models import AnimalType, AnimalGroup, AnimalEvent


class AnimalTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnimalType
        fields = ['id', 'name']


class AnimalGroupSerializer(serializers.ModelSerializer):
    animal_type_name = serializers.CharField(source='animal_type.name', read_only=True)
    farm_name = serializers.CharField(source='farm.name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = AnimalGroup
        fields = ['id', 'farm', 'farm_name', 'animal_type', 'animal_type_name', 'breed', 'count',
                  'birth_date', 'status', 'status_display', 'created_at', 'updated_at']

    def update(self, instance, validated_data):
        validated_data.pop('farm', None)  # guruhni boshqa fermaga ko'chirib bo'lmaydi
        return super().update(instance, validated_data)


class AnimalEventSerializer(serializers.ModelSerializer):
    days_since_start = serializers.ReadOnlyField()
    recorded_by_username = serializers.CharField(source='recorded_by.username', read_only=True, default=None)
    recorded_by_name = serializers.SerializerMethodField()
    event_type_display = serializers.CharField(source='get_event_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    animal_group_label = serializers.SerializerMethodField()
    animal_group_count = serializers.IntegerField(source='animal_group.count', read_only=True)
    farm = serializers.IntegerField(source='animal_group.farm_id', read_only=True)

    class Meta:
        model = AnimalEvent
        fields = ['id', 'farm', 'animal_group', 'animal_group_label', 'animal_group_count',
                  'event_type', 'event_type_display', 'title', 'description',
                  'status', 'status_display', 'start_date', 'end_date',
                  'recorded_by', 'recorded_by_username', 'recorded_by_name',
                  'days_since_start', 'created_at', 'updated_at']
        read_only_fields = ['recorded_by', 'created_at', 'updated_at']

    def get_recorded_by_name(self, obj):
        user = obj.recorded_by
        if not user:
            return None
        return user.get_full_name() or user.username

    def get_animal_group_label(self, obj):
        group = obj.animal_group
        return f"{group.animal_type.name} ({group.breed})" if group.breed else group.animal_type.name

    def validate(self, attrs):
        start = attrs.get('start_date', getattr(self.instance, 'start_date', None))
        end = attrs.get('end_date', getattr(self.instance, 'end_date', None))
        status = attrs.get('status', getattr(self.instance, 'status', None))

        # Yakunlangan ishga tugash sanasi avtomatik qo'yiladi
        if status == 'yakunlangan' and not end:
            end = timezone.localdate()
            attrs['end_date'] = end

        if start and end and end < start:
            raise serializers.ValidationError(
                {'end_date': "Tugash sanasi boshlanish sanasidan oldin bo'lishi mumkin emas"})
        return attrs
