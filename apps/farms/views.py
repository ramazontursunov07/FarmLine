from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from .models import Farm, Worker
from .serializers import FarmSerializer, WorkerSerializer
from django.db.models import Q
from rest_framework.exceptions import PermissionDenied


class WorkerViewSet(viewsets.ModelViewSet):
    queryset = Worker.objects.all()
    serializer_class = WorkerSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        return Worker.objects.filter(
            Q(farm__owner=user) | Q(user=user)
        ).distinct()

    def perform_create(self, serializer):
        farm = serializer.validated_data.get('farm')

        if farm.owner != self.request.user:
            raise PermissionDenied("Siz faqat o'zingizning fermangizga ishchi qo'sha olasiz.")

        serializer.save()


class FarmViewSet(viewsets.ModelViewSet):
    queryset = Farm.objects.all()
    serializer_class = FarmSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        return Farm.objects.filter(
            Q(owner=user) | Q(workers__user=user)
        ).distinct()

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)
