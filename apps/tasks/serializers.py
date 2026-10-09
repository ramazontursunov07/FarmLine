from rest_framework import serializers
from django.utils import timezone

from apps.farms.models import Worker
from apps.users.models import User
from .models import Task


def _display_name(user):
    return (user.get_full_name() or user.username) if user else None


class TaskSerializer(serializers.ModelSerializer):
    assigned_to = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), required=False, allow_null=True,
    )
    assigned_to_name = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()
    completed_by_name = serializers.SerializerMethodField()
    priority_display = serializers.CharField(source='get_priority_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    farm_name = serializers.CharField(source='farm.name', read_only=True)
    is_overdue = serializers.SerializerMethodField()

    class Meta:
        model = Task
        fields = [
            'id', 'farm', 'farm_name', 'title', 'description',
            'assigned_to', 'assigned_to_name', 'due_date',
            'priority', 'priority_display', 'status', 'status_display',
            'result_note', 'is_overdue',
            'created_by', 'created_by_name', 'completed_by', 'completed_by_name',
            'completed_at', 'created_at', 'updated_at',
        ]
        read_only_fields = ['created_by', 'completed_by', 'completed_at', 'created_at', 'updated_at']

    def get_assigned_to_name(self, obj):
        return _display_name(obj.assigned_to) or "Barcha ishchilar"

    def get_created_by_name(self, obj):
        return _display_name(obj.created_by)

    def get_completed_by_name(self, obj):
        return _display_name(obj.completed_by)

    def get_is_overdue(self, obj):
        return bool(obj.due_date and obj.status != 'bajarildi' and obj.due_date < timezone.localdate())

    def validate(self, attrs):
        farm = attrs.get('farm') or (self.instance.farm if self.instance else None)
        assigned = attrs.get('assigned_to')
        if assigned and not Worker.objects.filter(farm=farm, user=assigned).exists():
            raise serializers.ValidationError({'assigned_to': "Bu odam shu fermaning ishchisi emas"})
        return attrs

    def update(self, instance, validated_data):
        validated_data.pop('farm', None)  # vazifani boshqa fermaga ko'chirib bo'lmaydi
        return super().update(instance, validated_data)
