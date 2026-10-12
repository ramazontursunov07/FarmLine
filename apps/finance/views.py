from django.db import transaction as db_transaction
from django.db.models import DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce, TruncDay, TruncMonth, TruncWeek, TruncYear
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.animals.models import AnimalGroup
from apps.farms.models import Farm
from apps.core.mixins import IdempotentCreateMixin
from apps.users.digest import money
from apps.users.notify import display_name, notify_users
from apps.users.permissions import is_app_admin
from .models import Transaction
from .serializers import TransactionSerializer


def finance_farms(user):
    """Foydalanuvchi kirim-chiqimini boshqara oladigan fermalar:
    o'zi egasi bo'lgan yoki moliyani ko'rish huquqi berilgan ishchi."""
    return Farm.objects.filter(
        Q(owner=user) | Q(workers__user=user, workers__can_view_finance=True)
    ).distinct()


class TransactionViewSet(IdempotentCreateMixin, viewsets.ModelViewSet):
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

    def _notify_owner(self, tx, action):
        """Kirim-chiqimni ferma egasiga Telegramda bildiradi (egasining o'z amallari haqida xabar yuborilmaydi)."""
        user = self.request.user
        owner = tx.farm.owner
        if user.id == owner.id:
            return
        icon = "💰" if tx.transaction_type == "kirim" else "💸"
        lines = [
            f"{icon} {tx.get_transaction_type_display()} {action} ({tx.farm.name})",
            f"Summa: {money(tx.amount)} so'm",
            f"Kategoriya: {tx.get_category_display()}",
            f"Sana: {tx.date:%d.%m.%Y}",
        ]
        if tx.animal_count:
            lines.append(f"Hayvon soni: {tx.animal_count} ta")
        if tx.description:
            lines.append(f"Izoh: {tx.description}")
        lines.append(f"Kim: {display_name(user)}")
        notify_users([owner], "\n".join(lines))

    def perform_create(self, serializer):
        self._ensure_can_write(serializer.validated_data["farm"])
        count = serializer.validated_data.get("animal_count")
        if not count:
            tx = serializer.save(recorded_by=self.request.user)
            self._notify_owner(tx, "qo'shildi")
            return

        # Sotuv: sotilgan hayvonlar soni guruhdan avtomatik ayriladi
        with db_transaction.atomic():
            group = AnimalGroup.objects.select_for_update().get(pk=serializer.validated_data["animal_group"].pk)
            if count > group.count:
                raise ValidationError({"animal_count": f"Guruhda faqat {group.count} ta hayvon bor"})
            group.count -= count
            if group.count == 0:
                group.status = "sotilgan"
            group.save(update_fields=["count", "status", "updated_at"])
            tx = serializer.save(recorded_by=self.request.user)
            self._notify_owner(tx, "qo'shildi")

    def perform_update(self, serializer):
        self._ensure_can_write(serializer.instance.farm)
        if "farm" in serializer.validated_data:
            self._ensure_can_write(serializer.validated_data["farm"])
        tx = serializer.save()
        self._notify_owner(tx, "o'zgartirildi")

    def perform_destroy(self, instance):
        self._ensure_can_write(instance.farm)
        self._notify_owner(instance, "o'chirildi")  # o'chirishdan oldin: ma'lumotlar hali bor
        if not (instance.animal_count and instance.animal_group_id):
            instance.delete()
            return

        # Sotuv yozuvi o'chirilsa, hayvonlar soni guruhga qaytariladi
        with db_transaction.atomic():
            group = AnimalGroup.objects.select_for_update().get(pk=instance.animal_group_id)
            group.count += instance.animal_count
            if group.status == "sotilgan":
                group.status = "faol"
            group.save(update_fields=["count", "status", "updated_at"])
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

    @action(detail=False, methods=["get"])
    def report(self, request):
        """Kunlik/haftalik/oylik/yillik foyda-zarar: ?period=day|week|month|year
        (+ summary dagi filtrlar: farm, date_from, date_to, ...)."""
        trunc = {"day": TruncDay, "week": TruncWeek, "month": TruncMonth, "year": TruncYear}
        period = request.query_params.get("period", "month")
        if period not in trunc:
            return Response({"detail": "period: day, week, month yoki year bo'lishi kerak"}, status=400)

        zero = Value(0, output_field=DecimalField())
        qs = self.filter_queryset(self.get_queryset()).order_by()
        rows = (
            qs.annotate(p=trunc[period]("date"))
            .values("p")
            .annotate(
                income=Coalesce(Sum("amount", filter=Q(transaction_type="kirim")), zero),
                expense=Coalesce(Sum("amount", filter=Q(transaction_type="chiqim")), zero),
            )
            .order_by("-p")
        )
        return Response([
            {
                "period": r["p"].isoformat(),
                "income": r["income"],
                "expense": r["expense"],
                "profit": r["income"] - r["expense"],
            }
            for r in rows
        ])
