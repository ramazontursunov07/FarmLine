from rest_framework import viewsets
from .serializers import TransactionSerializer
from django.db.models import Q
from .models import Transaction
from rest_framework.permissions import IsAuthenticated


class TransactionViewSet(viewsets.ModelViewSet):
    queryset = Transaction.objects.all()
    serializer_class = TransactionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        return Transaction.objects.filter(
            Q(farm__owner=user) |
            Q(farm__workers__user=user, farm__workers__can_view_finance=True)
        ).distinct()

    def perform_create(self, serializer):
        serializer.save(recorded_by=self.request.user)
