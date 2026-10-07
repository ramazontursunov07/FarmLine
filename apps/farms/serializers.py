from rest_framework import serializers
from .models import Farm, Worker


class FarmSerializer(serializers.ModelSerializer):
    owner_username = serializers.CharField(source='owner.username', read_only=True)

    class Meta:
        model = Farm
        fields = ['id', 'owner', 'owner_username', 'name', 'location', 'farm_type', 'created_at', 'updated_at']
        read_only_fields = ['owner']


class WorkerSerializer(serializers.ModelSerializer):
    user_username = serializers.CharField(source='user.username', read_only=True)
    farm_name = serializers.CharField(source='farm.name', read_only=True)

    class Meta:
        model = Worker
        fields = ['id', 'user', 'user_username', 'farm_name', 'farm', 'can_view_finance', 'joined_at']
