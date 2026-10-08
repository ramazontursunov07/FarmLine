from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from rest_framework import serializers

from apps.users.models import User
from .models import Farm, Worker


class FarmSerializer(serializers.ModelSerializer):
    owner_username = serializers.CharField(source='owner.username', read_only=True)
    can_view_finance = serializers.SerializerMethodField()

    class Meta:
        model = Farm
        fields = ['id', 'owner', 'owner_username', 'name', 'location', 'farm_type',
                  'can_view_finance', 'created_at', 'updated_at']
        read_only_fields = ['owner']

    def get_can_view_finance(self, obj):
        """Fermer o'z fermasida har doim True; ishchida esa unga berilgan huquq."""
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return False
        if obj.owner_id == user.id:
            return True
        return obj.workers.filter(user=user, can_view_finance=True).exists()


class WorkerSerializer(serializers.ModelSerializer):
    """Ishchini ko'rsatish va tahrirlash (tahrirlanadigan yagona maydon: can_view_finance)."""
    user_username = serializers.CharField(source='user.username', read_only=True)
    user_full_name = serializers.SerializerMethodField()
    user_phone = serializers.CharField(source='user.phone_number', read_only=True, default='')
    farm_name = serializers.CharField(source='farm.name', read_only=True)

    class Meta:
        model = Worker
        fields = [
            'id', 'user', 'user_username', 'user_full_name', 'user_phone',
            'farm_name', 'farm', 'can_view_finance', 'joined_at',
        ]
        read_only_fields = ['user', 'farm']

    def get_user_full_name(self, obj):
        return obj.user.get_full_name() or obj.user.username


class WorkerCreateSerializer(serializers.Serializer):
    """Fermer ishchi uchun yangi akkaunt ochadi va uni fermaga biriktiradi."""
    farm = serializers.PrimaryKeyRelatedField(queryset=Farm.objects.all())
    username = serializers.CharField(
        max_length=150,
        validators=User._meta.get_field('username').validators,
    )
    password = serializers.CharField(write_only=True, validators=[validate_password])
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True, default='')
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True, default='')
    phone_number = serializers.CharField(max_length=20, required=False, allow_blank=True, default='')
    can_view_finance = serializers.BooleanField(required=False, default=False)

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("Bu username band. Boshqasini tanlang.")
        return value

    @transaction.atomic
    def create(self, validated_data):
        farm = validated_data['farm']
        user = User.objects.create_user(
            username=validated_data['username'],
            password=validated_data['password'],
            first_name=validated_data['first_name'],
            last_name=validated_data['last_name'],
            phone_number=validated_data['phone_number'] or None,
            role='ishchi',
        )
        return Worker.objects.create(
            user=user,
            farm=farm,
            can_view_finance=validated_data['can_view_finance'],
        )
