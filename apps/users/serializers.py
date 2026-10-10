from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import User


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)

        data['user'] = {
            'id': self.user.id,
            'username': self.user.username,
            'first_name': self.user.first_name,
            'last_name': self.user.last_name,
            'email': self.user.email,
            'role': self.user.role,
        }

        return data


class RegisterSerializer(serializers.ModelSerializer):
    """Ro'yxatdan o'tish. 'role' kiritilmaydi, hamma fermer bo'lib ro'yxatdan o'tadi."""
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name', 'email', 'phone_number', 'password', 'password2']

    def validate(self, attrs):
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({'password2': 'Parollar bir xil emas'})
        return attrs

    def create(self, validated_data):
        validated_data.pop('password2')
        return User.objects.create_user(**validated_data)


class ChangePasswordSerializer(serializers.ModelSerializer):
    """Parol o'zgartirish"""
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ['old_password', 'new_password']

    def validate_new_password(self, value):
        validate_password(value, user=self.context['request'].user)
        return value

    def validate(self, attrs):
        if attrs['old_password'] == attrs['new_password']:
            raise serializers.ValidationError({'new_password': "Yangi parol eskisidan farq qilishi kerak"})
        return attrs


class UserUpdateSerializer(serializers.ModelSerializer):
    """Profilni yangilash. 'telegram_linked' faqat o'qish uchun: Telegram ulanganmi?"""
    telegram_linked = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['username', 'role', 'first_name', 'last_name', 'email', 'phone_number', 'telegram_linked']
        read_only_fields = ['username', 'role', 'telegram_linked']

    def get_telegram_linked(self, obj):
        return bool(obj.telegram_chat_id)


class ForgotPasswordSerializer(serializers.Serializer):
    """
    Faqat username qabul qiladi. Foydalanuvchi bor-yo'qligi bu yerda TEKSHIRILMAYDI,
    aks holda begona odam username'larni aniqlab olishi mumkin.
    """
    username = serializers.CharField()


class ResetPasswordSerializer(serializers.Serializer):
    """Token orqali yangi parol o'rnatish"""
    token = serializers.UUIDField()
    new_password = serializers.CharField(write_only=True, validators=[validate_password])


class AdminUserListSerializer(serializers.ModelSerializer):
    """Admin panel uchun foydalanuvchilar ro'yxati"""
    farms_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name', 'email', 'phone_number',
                  'role', 'date_joined', 'farms_count']
