from rest_framework.permissions import BasePermission
from apps.farms.models import Worker


class IsFarmOwnerOrWorker(BasePermission):
    """
    Faqat fermaning egasi (fermer) yoki o'sha fermaga tayinlangan
    ishchi (worker) ma'lumotlarni ko'rishi/o'zgartirishi mumkin.
    """

    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        # AnimalGroup uchun farm to'g'ridan-to'g'ri bor,
        # AnimalEvent uchun esa animal_group orqali olinadi
        if hasattr(obj, 'farm'):
            farm = obj.farm
        elif hasattr(obj, 'animal_group'):
            farm = obj.animal_group.farm
        else:
            return False

        # Fermer (xo'jalik egasi) bo'lsa
        if farm.owner == request.user:
            return True

        # Ishchi sifatida shu fermaga tayinlangan bo'lsa
        if Worker.objects.filter(farm=farm, user=request.user).exists():
            return True

        return False
