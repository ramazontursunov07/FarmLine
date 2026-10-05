from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from .serializers import InventoryItemSerializer, InventoryTransactionSerializer
from .models import InventoryItem, InventoryTransaction
from django.db.models import Q


class InventoryItemViewSet(viewsets.ModelViewSet):
    queryset = InventoryItem.objects.all()
    serializer_class = InventoryItemSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        return InventoryItem.objects.filter(
            Q(farm__owner=user) |
            Q(farm__workers__user=user)
        ).distinct()

    def perform_create(self, serializer):
        serializer.save()


class InventoryTransactionViewSet(viewsets.ModelViewSet):
    queryset = InventoryTransaction.objects.all()
    serializer_class = InventoryTransactionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        return InventoryTransaction.objects.filter(
            Q(inventory_item__farm__owner=user) |
            Q(inventory_item__farm__workers__user=user)
        ).distinct()

    def perform_create(self, serializer):
        serializer.save(recorded_by=self.request.user)
