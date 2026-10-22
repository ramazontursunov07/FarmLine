import re

from django.db import transaction as db_transaction
from django.http import HttpResponse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.db.models import DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce, TruncDay, TruncMonth, TruncWeek, TruncYear
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from apps.animals.models import AnimalGroup
from apps.debts import credit
from apps.farms.models import Farm
from apps.core.mixins import IdempotentCreateMixin
from apps.users.digest import money
from apps.users.notify import display_name, notify_users
from apps.users.permissions import is_app_admin
from . import report as report_builder
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
            if not p["farm"].isdigit():
                raise ValidationError({"farm": "Ferma raqami noto'g'ri."})
            queryset = queryset.filter(farm_id=p["farm"])
        if p.get("transaction_type"):
            queryset = queryset.filter(transaction_type=p["transaction_type"])
        if p.get("category"):
            queryset = queryset.filter(category=p["category"])
        for key, lookup in (("date_from", "date__gte"), ("date_to", "date__lte")):
            if p.get(key):
                try:
                    value = parse_date(p[key])
                except ValueError:
                    value = None
                if value is None:
                    raise ValidationError({key: "Sana YYYY-MM-DD ko'rinishida bo'lishi kerak."})
                queryset = queryset.filter(**{lookup: value})
        return queryset

    def get_throttles(self):
        # Hisobot fayli og'ir (PDF/Excel yasaydi): faqat shu amalga soatiga cheklov
        if self.action == "export":
            self.throttle_scope = "export"
            return [ScopedRateThrottle()]
        return super().get_throttles()

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

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        debt = getattr(self, "_credit_debt", None)
        if debt is not None:
            response.data["on_credit"] = True
            response.data["debt"] = debt.pk
        return response

    def _create_on_credit(self, serializer, credit_info):
        """
        Nasiyaga sotish (kirim) yoki nasiyaga olish (chiqim): balansga hozir ta'sir qilmaydi, qarz ochiladi.
        Sotilgan hayvonlar soni esa darhol guruhdan ayriladi (qarz o'chirilsa, qaytadi).
        """
        data = serializer.validated_data
        kind = "mijoz" if data["transaction_type"] == "kirim" else "taminotchi"
        count = data.get("animal_count")
        group = data.get("animal_group")
        with db_transaction.atomic():
            if count:
                group = AnimalGroup.objects.select_for_update().get(pk=group.pk)
                if count > group.count:
                    raise ValidationError({"animal_count": f"Guruhda faqat {group.count} ta hayvon bor"})
                group.count -= count
                if group.count == 0:
                    group.status = "sotilgan"
                group.save(update_fields=["count", "status", "updated_at"])
            description = data.get("description") or data["category"]
            if count:
                description = f"{count} ta hayvon" + (f": {data['description']}" if data.get("description") else "")
            debt = credit.open_credit(
                farm=data["farm"], kind=kind, credit=credit_info, total=data["amount"], date=data["date"],
                description=description, user=self.request.user, category=data["category"],
                animal_group=group if count else None, animal_count=count)
        self._credit_debt = debt
        # Javob uchun saqlanmagan yozuv: moliya ro'yxatiga qo'shilmaydi, chunki pul hali kelmagan/ketmagan
        serializer.instance = Transaction(**{k: v for k, v in data.items()}, recorded_by=self.request.user)

    def perform_create(self, serializer):
        self._ensure_can_write(serializer.validated_data["farm"])
        if credit.parse_credit_flag(self.request.data):
            data = serializer.validated_data
            credit_info = credit.parse_credit(self.request.data, data["farm"], data["amount"], data["date"])
            self._create_on_credit(serializer, credit_info)
            return
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

    @action(detail=False, methods=["get"])
    def export(self, request):
        """Oylik hisobotni fayl qilib beradi: ?farm=1&month=2026-10&file=xlsx|pdf
        (month bo'lmasa -- shu oy). Kirim-chiqim huquqi bor foydalanuvchi yoki admin ko'ra oladi."""
        p = request.query_params
        if not (p.get("farm") or "").isdigit():
            raise ValidationError({"farm": "Ferma raqami kerak."})

        user = request.user
        farms = Farm.objects.all() if is_app_admin(user) else finance_farms(user)
        farm = farms.filter(pk=p["farm"]).first()
        if farm is None:
            raise NotFound("Ferma topilmadi.")

        file_type = (p.get("file") or "xlsx").lower()
        if file_type not in ("xlsx", "pdf"):
            raise ValidationError({"file": "file: xlsx yoki pdf bo'lishi kerak."})

        month_value = p.get("month") or timezone.localdate().strftime("%Y-%m")
        match = re.fullmatch(r"(\d{4})-(\d{2})", month_value)
        if not match or not (1 <= int(match.group(2)) <= 12) or not (2000 <= int(match.group(1)) <= 2100):
            raise ValidationError({"month": "Oy YYYY-MM ko'rinishida bo'lishi kerak (masalan, 2026-10)."})
        year, month = int(match.group(1)), int(match.group(2))

        data = report_builder.collect(farm, year, month, generated_by=user)
        if file_type == "pdf":
            content, content_type = report_builder.build_pdf(data), "application/pdf"
        else:
            content = report_builder.build_xlsx(data)
            content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

        response = HttpResponse(content, content_type=content_type)
        response["Content-Disposition"] = f'attachment; filename="farmline-{farm.pk}-{month_value}.{file_type}"'
        response["Cache-Control"] = "no-store"
        return response
    