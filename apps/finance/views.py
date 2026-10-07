from django.db.models import Q, Sum
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.farms.models import Farm
from apps.users.permissions import is_app_admin
from .models import Transaction
from .serializers import TransactionSerializer


def finance_farms(user):
    """Foydalanuvchi kirim-chiqimini boshqara oladigan fermalar:
    o'zi egasi bo'lgan yoki moliyani ko'rish huquqi berilgan ishchi."""
    return Farm.objects.filter(
        Q(owner=user) | Q(workers__user=user, workers__can_view_finance=True)
    ).distinct()


class TransactionViewSet(viewsets.ModelViewSet):
    queryset = Transaction.objects.all()
    serializer_class = TransactionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if is_app_admin(user):
            qs = Transaction.objects.all()  # admin hammasini ko'radi
        else:
            qs = Transaction.objects.filter(farm__in=finance_farms(user))
        return qs.select_related("farm", "recorded_by", "animal_group__animal_type", "animal_group__farm") \
                 .order_by("-date", "-id")

    def filter_queryset(self, queryset):
        """?farm=1&transaction_type=kirim&category=ozuqa&date_from=2026-01-01&date_to=2026-12-31"""
        p = self.request.query_params
        if p.get("farm"):
            queryset = queryset.filter(farm_id=p["farm"])
        if p.get("transaction_type"):
            queryset = queryset.filter(transaction_type=p["transaction_type"])
        if p.get("category"):
            queryset = queryset.filter(category=p["category"])
        if p.get("date_from"):
            queryset = queryset.filter(date__gte=p["date_from"])
        if p.get("date_to"):
            queryset = queryset.filter(date__lte=p["date_to"])
        return queryset

    # --- yozish huquqi: faqat ferma egasi yoki moliya huquqi bor ishchi (admin faqat ko'radi) ---
    def _ensure_can_write(self, farm):
        if not finance_farms(self.request.user).filter(pk=farm.pk).exists():
            raise PermissionDenied("Siz bu fermaning kirim-chiqimini o'zgartira olmaysiz.")

    def perform_create(self, serializer):
        self._ensure_can_write(serializer.validated_data["farm"])
        serializer.save(recorded_by=self.request.user)

    def perform_update(self, serializer):
        self._ensure_can_write(serializer.instance.farm)
        if "farm" in serializer.validated_data:
            self._ensure_can_write(serializer.validated_data["farm"])
        serializer.save()

    def perform_destroy(self, instance):
        self._ensure_can_write(instance.farm)
        instance.delete()

    @action(detail=False, methods=["get"])
    def summary(self, request):
        """Jami kirim, chiqim, balans va kategoriyalar kesimi (xuddi shu filtrlar bilan)."""
        qs = self.filter_queryset(self.get_queryset()).order_by()
        by_category = list(
            qs.values("transaction_type", "category").annotate(total=Sum("amount")).order_by("-total")
        )
        income = sum(r["total"] for r in by_category if r["transaction_type"] == "kirim")
        expense = sum(r["total"] for r in by_category if r["transaction_type"] == "chiqim")
        return Response({
            "income": income,
            "expense": expense,
            "balance": income - expense,
            "by_category": by_category,
        })
