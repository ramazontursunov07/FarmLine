from django.db.models import Q
from rest_framework import status, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.users.permissions import is_app_admin
from .models import Farm, Worker
from .serializers import FarmSerializer, WorkerCreateSerializer, WorkerSerializer


class WorkerViewSet(viewsets.ModelViewSet):
    """
    Ishchilar. Faqat ferma egasi ishchi qo'sha, tahrirlay va olib tashlay oladi.
    Ishchining o'zi faqat o'z yozuvini ko'ra oladi. ?farm=<id> bilan filtrlanadi.
    """
    queryset = Worker.objects.all()
    serializer_class = WorkerSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = Worker.objects.select_related('user', 'farm').filter(
            Q(farm__owner=user) | Q(user=user)
        ).distinct()
        farm_id = self.request.query_params.get('farm')
        if farm_id and farm_id.isdigit():
            qs = qs.filter(farm_id=int(farm_id))
        return qs

    def create(self, request, *args, **kwargs):
        serializer = WorkerCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        farm = serializer.validated_data['farm']
        if farm.owner != request.user:
            raise PermissionDenied("Siz faqat o'zingizning fermangizga ishchi qo'sha olasiz.")

        worker = serializer.save()
        data = WorkerSerializer(worker, context=self.get_serializer_context()).data
        return Response(data, status=status.HTTP_201_CREATED)

    def _ensure_owner(self, worker):
        if worker.farm.owner != self.request.user:
            raise PermissionDenied("Faqat ferma egasi ishchini o'zgartira yoki olib tashlay oladi.")

    def perform_update(self, serializer):
        self._ensure_owner(serializer.instance)
        serializer.save()

    def perform_destroy(self, instance):
        self._ensure_owner(instance)
        user = instance.user
        instance.delete()
        # Ishchi boshqa hech qaysi fermada qolmagan bo'lsa, akkaunt bloklanadi
        # (o'chirilmaydi, shunda uning yozgan kirim-chiqim tarixi saqlanib qoladi).
        if user.role == 'ishchi' and not user.worker_profiles.exists():
            user.is_active = False
            user.save(update_fields=['is_active'])


class FarmViewSet(viewsets.ModelViewSet):
    queryset = Farm.objects.all()
    serializer_class = FarmSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if is_app_admin(user):
            return Farm.objects.select_related('owner').all()
        return Farm.objects.select_related('owner').filter(
            Q(owner=user) | Q(workers__user=user)
        ).distinct()

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    # --- faqat ferma egasi tahrirlay va o'chira oladi (ishchi va admin faqat ko'radi) ---
    def _ensure_owner(self, farm):
        if farm.owner != self.request.user:
            raise PermissionDenied("Faqat ferma egasi uni o'zgartira yoki o'chira oladi.")

    def perform_update(self, serializer):
        self._ensure_owner(serializer.instance)
        serializer.save()

    def perform_destroy(self, instance):
        self._ensure_owner(instance)
        instance.delete()
