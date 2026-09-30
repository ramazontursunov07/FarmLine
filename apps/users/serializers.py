from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from .models import User


class UserSerializer(serializers.ModelSerializer):
    """User yaratish"""

    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name', 'email', 'password', 'role', 'phone_number']

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

    def create(self, validated_data):
        validated_data.pop('password2')
        return User.objects.create_user(**validated_data)


class ChangePasswordSerializer(serializers.ModelSerializer):
    """Parol o'zgartirish"""
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)


class UserUpdateSerializer(serializers.ModelSerializer):
    """Profilni yangilash"""

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'phone_number']
