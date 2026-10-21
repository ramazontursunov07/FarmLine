"""Qarz hisob-kitobi: bir joyda, API ham, Telegram eslatma ham shundan foydalanadi."""
from decimal import Decimal

from django.db.models import DecimalField, Sum, Value
from django.db.models.functions import Coalesce

from .models import Debt

ZERO = Decimal('0')
DUE_SOON_DAYS = 3  # muddatga shuncha kun qolsa, Telegramda eslatiladi


def debts_with_paid(farm_ids=None, **filters):
    """Qarzlar, har biriga `paid_total` (to'langan jami) qo'shilgan holda."""
    qs = Debt.objects.select_related('party')
    if farm_ids is not None:
        qs = qs.filter(farm_id__in=farm_ids)
    if filters:
        qs = qs.filter(**filters)
    return qs.annotate(
        paid_total=Coalesce(Sum('payments__amount'), Value(ZERO),
                            output_field=DecimalField(max_digits=14, decimal_places=2))
    )


def remaining(debt):
    return debt.amount - (getattr(debt, 'paid_total', None) or ZERO)


def is_overdue(debt, today):
    return debt.due_date is not None and debt.due_date < today and remaining(debt) > 0


def days_overdue(debt, today):
    return (today - debt.due_date).days if is_overdue(debt, today) else 0


def totals(debts, today):
    """Qarzlar ro'yxati bo'yicha umumiy raqamlar."""
    amount = paid = overdue_amount = ZERO
    overdue_count = open_count = 0
    for d in debts:
        p = getattr(d, 'paid_total', None) or ZERO
        left = d.amount - p
        amount += d.amount
        paid += p
        if left > 0:
            open_count += 1
            if is_overdue(d, today):
                overdue_count += 1
                overdue_amount += left
    return {
        'amount': amount, 'paid': paid, 'remaining': amount - paid,
        'open_count': open_count, 'overdue_count': overdue_count, 'overdue_amount': overdue_amount,
    }
