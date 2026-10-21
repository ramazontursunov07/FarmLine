from decimal import Decimal

from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.core.mixins import IdempotentCreateMixin
from apps.farms.models import Farm
from apps.finance.views import finance_farms
from apps.users.permissions import is_app_admin

from . import stats
from .models import Debt, DebtPayment, Party
from .serializers import DebtSerializer, PartySerializer, PaymentSerializer


def readable_farms(user):
    """Qarzlarni ko'ra oladigan fermalar: egasi, moliya huquqi bor ishchi (admin hammasini)."""
    return Farm.objects.all() if is_app_admin(user) else finance_farms(user)


def ensure_can_write(user, farm):
    """Yozish: faqat ferma egasi yoki moliya huquqi bor ishchi (admin faqat ko'radi)."""
    if not finance_farms(user).filter(pk=farm.pk).exists():
        raise PermissionDenied("Siz bu fermaning qarzlarini o'zgartira olmaysiz.")


def farm_param(request):
    value = request.query_params.get('farm')
    if value:
        if not value.isdigit():
            raise ValidationError({'farm': "Ferma raqami noto'g'ri."})
        return int(value)
    return None


def money(value):
    return str(Decimal(value).quantize(Decimal('0.01')))


def totals_json(t):
    return {k: (money(v) if k in ('amount', 'paid', 'remaining', 'overdue_amount') else v) for k, v in t.items()}


class PartyViewSet(IdempotentCreateMixin, viewsets.ModelViewSet):
    """Mijozlar va yetkazib beruvchilar. ?farm=1&kind=mijoz"""
    queryset = Party.objects.all()
    serializer_class = PartySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Party.objects.filter(farm__in=readable_farms(self.request.user))

    def filter_queryset(self, queryset):
        farm = farm_param(self.request)
        if farm:
            queryset = queryset.filter(farm_id=farm)
        kind = self.request.query_params.get('kind')
        if kind:
            queryset = queryset.filter(kind=kind)
        return queryset

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if self.action in ('list', 'retrieve'):
            parties = self.filter_queryset(self.get_queryset())
            today = timezone.localdate()
            by_party = {}
            for debt in stats.debts_with_paid(party__in=parties):
                by_party.setdefault(debt.party_id, []).append(debt)
            context['party_totals'] = {pk: stats.totals(items, today) for pk, items in by_party.items()}
        return context

    def perform_create(self, serializer):
        ensure_can_write(self.request.user, serializer.validated_data['farm'])
        serializer.save()

    def perform_update(self, serializer):
        ensure_can_write(self.request.user, serializer.instance.farm)
        serializer.save()

    def perform_destroy(self, instance):
        ensure_can_write(self.request.user, instance.farm)
        if instance.debts.exists():
            raise ValidationError(
                "Bu odamning qarz yozuvlari bor. Avval qarzlarini o'chiring, keyin odamni o'chirish mumkin.")
        instance.delete()


class DebtViewSet(IdempotentCreateMixin, viewsets.ModelViewSet):
    """
    Qarzlar. ?farm=1&party=3&kind=mijoz&status=open|overdue|closed
    """
    queryset = Debt.objects.all()
    serializer_class = DebtSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        farms = readable_farms(self.request.user).values('pk')
        return stats.debts_with_paid(farm_id__in=farms).prefetch_related('payments').order_by('-date', '-id')

    def filter_queryset(self, queryset):
        p = self.request.query_params
        farm = farm_param(self.request)
        if farm:
            queryset = queryset.filter(farm_id=farm)
        if p.get('party'):
            if not p['party'].isdigit():
                raise ValidationError({'party': "Noto'g'ri raqam."})
            queryset = queryset.filter(party_id=p['party'])
        if p.get('kind'):
            queryset = queryset.filter(party__kind=p['kind'])
        status = p.get('status')
        if status == 'open':
            queryset = queryset.filter(paid_total__lt=F('amount'))
        elif status == 'closed':
            queryset = queryset.filter(paid_total__gte=F('amount'))
        elif status == 'overdue':
            queryset = queryset.filter(paid_total__lt=F('amount'), due_date__lt=timezone.localdate())
        elif status:
            raise ValidationError({'status': "open, overdue yoki closed bo'lishi kerak."})
        return queryset

    def perform_create(self, serializer):
        party = serializer.validated_data['party']
        ensure_can_write(self.request.user, party.farm)
        serializer.save(farm=party.farm, recorded_by=self.request.user)

    def perform_update(self, serializer):
        ensure_can_write(self.request.user, serializer.instance.farm)
        serializer.save()

    def perform_destroy(self, instance):
        ensure_can_write(self.request.user, instance.farm)
        instance.delete()  # to'lovlari ham o'chadi

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Bitta ferma bo'yicha umumiy: `?farm=1`. Mijozlar (bizga qarz) va yetkazib beruvchilar (biz qarzmiz) alohida."""
        farm = farm_param(request)
        if not farm:
            raise ValidationError({'farm': "Fermani ko'rsating (?farm=)"})
        if not readable_farms(request.user).filter(pk=farm).exists():
            raise PermissionDenied("Siz bu fermaning qarzlarini ko'ra olmaysiz.")
        today = timezone.localdate()
        debts = list(stats.debts_with_paid(farm_id=farm))
        return Response({
            'farm': farm,
            'receivable': totals_json(stats.totals([d for d in debts if d.party.kind == 'mijoz'], today)),
            'payable': totals_json(stats.totals([d for d in debts if d.party.kind == 'taminotchi'], today)),
        })

    @action(detail=False, methods=['get'])
    def overview(self, request):
        """Bosh sahifa uchun: har bir ferma bo'yicha muddati o'tgan qarzlar va qoldiq (faqat ochiq qarzlar)."""
        today = timezone.localdate()
        farms = readable_farms(request.user).values('pk')
        by_farm = {}
        for d in stats.debts_with_paid(farm_id__in=farms):
            by_farm.setdefault(d.farm_id, []).append(d)
        out = []
        for farm_id, items in by_farm.items():
            recv = stats.totals([d for d in items if d.party.kind == 'mijoz'], today)
            pay = stats.totals([d for d in items if d.party.kind == 'taminotchi'], today)
            out.append({
                'farm': farm_id,
                'overdue_count': recv['overdue_count'] + pay['overdue_count'],
                'receivable_remaining': money(recv['remaining']),
                'payable_remaining': money(pay['remaining']),
            })
        return Response(out)


class DebtPaymentViewSet(IdempotentCreateMixin, viewsets.ModelViewSet):
    """Qarzga to'lov. ?debt=5"""
    queryset = DebtPayment.objects.all()
    serializer_class = PaymentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        farms = readable_farms(self.request.user).values('pk')
        return DebtPayment.objects.filter(debt__farm_id__in=farms)

    def filter_queryset(self, queryset):
        debt = self.request.query_params.get('debt')
        if debt:
            if not debt.isdigit():
                raise ValidationError({'debt': "Noto'g'ri raqam."})
            queryset = queryset.filter(debt_id=debt)
        return queryset

    @staticmethod
    def _check_not_overpaid(debt_id, new_amount, exclude_pk=None):
        """Qarz qulflanadi: ikki kishi bir vaqtda to'lasa ham jami summa qarzdan oshmaydi."""
        debt = Debt.objects.select_for_update().get(pk=debt_id)
        paid = debt.payments.exclude(pk=exclude_pk).aggregate(s=Sum('amount'))['s'] or Decimal('0')
        left = debt.amount - paid
        if new_amount > left:
            raise ValidationError({'amount': (
                f"To'lov qarzning qolgan qismidan ({money(left)}) oshib ketmasin" if left > 0
                else "Bu qarz to'liq to'langan")})

    def perform_create(self, serializer):
        debt = serializer.validated_data['debt']
        ensure_can_write(self.request.user, debt.farm)
        with transaction.atomic():
            self._check_not_overpaid(debt.pk, serializer.validated_data['amount'])
            serializer.save(recorded_by=self.request.user)

    def perform_update(self, serializer):
        payment = serializer.instance
        ensure_can_write(self.request.user, payment.debt.farm)
        with transaction.atomic():
            if 'amount' in serializer.validated_data:
                self._check_not_overpaid(payment.debt_id, serializer.validated_data['amount'], exclude_pk=payment.pk)
            serializer.save()

    def perform_destroy(self, instance):
        ensure_can_write(self.request.user, instance.debt.farm)
        instance.delete()
        