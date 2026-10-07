from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from .models import User
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer


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


class UserSerializer(serializers.ModelSerializer):
    """User yaratish"""

    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name', 'email', 'password', 'role', 'phone_number',
                  'telegram_chat_id']

        extra_kwargs = {
            'password': {'write_only': True},
        }

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class RegisterSerializer(serializers.ModelSerializer):
    """Registratsiya"""
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


class UserUpdateSerializer(serializers.ModelSerializer):
    """Profilni yangilash"""

    class Meta:
        model = User
        fields = ['username', 'role', 'first_name', 'last_name', 'email', 'phone_number']
        read_only_fields = ['username', 'role']


from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from .models import User


class ForgotPasswordSerializer(serializers.Serializer):
    """Parolni unutganda - foydalanuvchini aniqlash uchun"""
    username = serializers.CharField()

    def validate_username(self, value):
        if not User.objects.filter(username=value).exists():
            raise serializers.ValidationError("Bunday foydalanuvchi topilmadi")
        return value


class ResetPasswordSerializer(serializers.Serializer):
    """Token orqali yangi parol o'rnatish"""
    token = serializers.UUIDField()
    new_password = serializers.CharField(write_only=True, validators=[validate_password])
