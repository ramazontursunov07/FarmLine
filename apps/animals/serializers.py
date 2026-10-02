from rest_framework import serializers
from .models import AnimalType, AnimalGroup, AnimalEvent


class AnimalTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnimalType
        fields = ['id', 'name']


class AnimalEventSerializer(serializers.ModelSerializer):
    days_since_start = serializers.ReadOnlyField()
    recorded_by_username = serializers.CharField(source='recorded_by.username', read_only=True)

    class Meta:
        model = AnimalEvent
        fields = ['id', 'animal_group', 'event_type', 'title', 'description', 'status', 'start_date', 'end_date',
                  'recorded_by', 'recorded_by_username', 'days_since_start', 'created_at', 'updated_at']

        read_only_fields = ['recorded_by', 'created_at', 'updated_at']


class AnimalGroupSerializer(serializers.ModelSerializer):
    animal_type_name = serializers.CharField(source='animal_type.name', read_only=True)
    events = AnimalEventSerializer(many=True, read_only=True)


class Meta:
    model = AnimalGroup
    fields = ['id', 'farm', 'animal_type', 'animal_type_name', 'breed', 'count', 'birth_date', 'status', 'events',
              'created_at', 'updated_at']
