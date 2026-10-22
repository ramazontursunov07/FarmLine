from django.utils import timezone
from rest_framework import serializers

from . import stats
from .models import Debt, DebtPayment, Party


def _money(value):
    return str(value.quantize(stats.Decimal('0.01')))


class PartySerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(source='get_kind_display', read_only=True)
    # Ro'yxat view'i hisoblab beradi (har bir tomon uchun alohida so'rov bo'lmasligi uchun); bo'lmasa None
    totals = serializers.SerializerMethodField()

    class Meta:
        model = Party
        fields = ['id', 'farm', 'kind', 'kind_display', 'name', 'phone', 'note', 'totals', 'created_at']
        read_only_fields = ['created_at']

    def get_totals(self, obj):
        data = self.context.get('party_totals', {}).get(obj.pk)
        if data is None:
            return None
        return {k: (_money(v) if k in ('amount', 'paid', 'remaining', 'overdue_amount') else v) for k, v in
                data.items()}

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Ismni kiriting")
        return value

    def validate(self, attrs):
        farm = attrs.get('farm', getattr(self.instance, 'farm', None))
        kind = attrs.get('kind', getattr(self.instance, 'kind', 'mijoz'))
        name = attrs.get('name', getattr(self.instance, 'name', None))
        if self.instance is not None and 'farm' in attrs and attrs['farm'].pk != self.instance.farm_id:
            raise serializers.ValidationError({'farm': "Boshqa fermaga ko'chirib bo'lmaydi"})
        clash = Party.objects.filter(farm=farm, kind=kind, name__iexact=name)
        if self.instance is not None:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise serializers.ValidationError({'name': "Bu ism ro'yxatda allaqachon bor"})
        return attrs


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = DebtPayment
        fields = ['id', 'debt', 'amount', 'date', 'note', 'created_at']
        read_only_fields = ['created_at']

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Summa 0 dan katta bo'lishi kerak")
        return value

    def validate_date(self, value):
        if value > timezone.localdate():
            raise serializers.ValidationError("To'lov sanasi kelajakda bo'lishi mumkin emas")
        return value

    def validate(self, attrs):
        debt = attrs.get('debt', getattr(self.instance, 'debt', None))
        if self.instance is not None and 'debt' in attrs and attrs['debt'].pk != self.instance.debt_id:
            raise serializers.ValidationError({'debt': "Boshqa qarzga ko'chirib bo'lmaydi"})
        if 'date' in attrs and debt is not None and attrs['date'] < debt.date:
            raise serializers.ValidationError({'date': "To'lov qarz berilgan sanadan oldin bo'lishi mumkin emas"})
        return attrs


class DebtSerializer(serializers.ModelSerializer):
    party_name = serializers.CharField(source='party.name', read_only=True)
    kind = serializers.CharField(source='party.kind', read_only=True)
    paid = serializers.SerializerMethodField()
    remaining = serializers.SerializerMethodField()
    is_overdue = serializers.SerializerMethodField()
    days_overdue = serializers.SerializerMethodField()
    payments = PaymentSerializer(many=True, read_only=True)

    class Meta:
        model = Debt
        fields = ['id', 'farm', 'party', 'party_name', 'kind', 'amount', 'paid', 'remaining', 'date', 'due_date',
                  'is_overdue', 'days_overdue', 'description', 'payments', 'affects_balance', 'created_at']
        read_only_fields = ['created_at', 'farm', 'affects_balance']

    def _paid(self, obj):
        value = getattr(obj, 'paid_total', None)
        if value is None:  # annotate qilinmagan (masalan, yangi yaratilgan) bo'lsa
            value = sum((p.amount for p in obj.payments.all()), stats.ZERO)
        return value

    def get_paid(self, obj):
        return _money(self._paid(obj))

    def get_remaining(self, obj):
        return _money(obj.amount - self._paid(obj))

    def get_is_overdue(self, obj):
        return obj.due_date is not None and obj.due_date < timezone.localdate() and obj.amount - self._paid(obj) > 0

    def get_days_overdue(self, obj):
        return (timezone.localdate() - obj.due_date).days if self.get_is_overdue(obj) else 0

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Summa 0 dan katta bo'lishi kerak")
        return value

    def validate_date(self, value):
        if value > timezone.localdate():
            raise serializers.ValidationError("Sana kelajakda bo'lishi mumkin emas")
        return value

    def validate(self, attrs):
        instance = self.instance
        date = attrs.get('date', getattr(instance, 'date', None))
        due = attrs.get('due_date', getattr(instance, 'due_date', None))
        if due and date and due < date:
            raise serializers.ValidationError({'due_date': "Muddat qarz sanasidan oldin bo'lishi mumkin emas"})
        if instance is not None:
            if 'party' in attrs and attrs['party'].pk != instance.party_id:
                raise serializers.ValidationError({'party': "Qarzni boshqa odamga o'tkazib bo'lmaydi"})
            paid = self._paid(instance)
            if 'amount' in attrs and attrs['amount'] < paid:
                raise serializers.ValidationError({'amount': (
                    f"Qarz summasi allaqachon to'langan summadan ({_money(paid)}) kam bo'lishi mumkin emas")})
        return attrs
