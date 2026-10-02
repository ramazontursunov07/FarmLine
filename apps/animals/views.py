from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from .models import AnimalGroup, AnimalEvent, AnimalType
from .permissions import IsFarmOwnerOrWorker
from .serializers import AnimalTypeSerializer, AnimalGroupSerializer, AnimalEventSerializer
from django.db.models import Q


class AnimalTypeViewSet(viewsets.ModelViewSet):
    queryset = AnimalType.objects.all()
    serializer_class = AnimalTypeSerializer
    permission_classes = [IsAuthenticated]


class AnimalGroupViewSet(viewsets.ModelViewSet):
    queryset = AnimalGroup.objects.all()
    serializer_class = AnimalGroupSerializer
    permission_classes = [IsAuthenticated, IsFarmOwnerOrWorker]

    def get_queryset(self):
        user = self.request.user
        return AnimalGroup.objects.filter(
            Q(farm__owner=user) | Q(farm__workers__user=user)
        ).distinct()


class AnimalEventViewSet(viewsets.ModelViewSet):
    queryset = AnimalEvent.objects.all()
    serializer_class = AnimalEventSerializer
    permission_classes = [IsAuthenticated, IsFarmOwnerOrWorker]

    def get_queryset(self):
        user = self.request.user
        return AnimalEvent.objects.filter(
            Q(animal_group__farm__owner=user) | Q(animal_group__farm__workers__user=user)
        ).distinct()
