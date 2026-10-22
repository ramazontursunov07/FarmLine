"""
Nasiya (qarz) bilan sotish va xarid qilish.

Qoida: balans faqat HAQIQIY pul bo'yicha o'zgaradi.
- Nasiyaga sotilsa: qarz ochiladi, pul to'langan sari moliyada "Kirim" bo'lib yoziladi.
- Nasiyaga olinsa: qarz ochiladi, pul to'langan sari moliyada "Chiqim" bo'lib yoziladi.
Oldindan to'langan qism (bo'lsa) darhol birinchi to'lov sifatida yoziladi.
"""
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework.exceptions import ValidationError

from apps.finance.models import Transaction as FinanceTransaction

from .models import Debt, DebtPayment, Party


def _truthy(value):
    return str(value).lower() in ('1', 'true', 'on', 'yes')


def parse_credit_flag(data):
    return _truthy(data.get('on_credit', ''))


def parse_credit(data, farm, total, date):
    """
    So'rov ichidan nasiya ma'lumotlarini o'qiydi: on_credit, party (id) yoki party_name, due_date, paid_now.
    Nasiya bo'lmasa None qaytaradi.
    """
    if not _truthy(data.get('on_credit', '')):
        return None
    party_id = data.get('party')
    name = (data.get('party_name') or '').strip()
    if not party_id and not name:
        raise ValidationError({'party': "Nasiya kimga/kimdan ekanini tanlang yoki ism yozing"})
    due_raw = data.get('due_date')
    due = parse_date(str(due_raw)) if due_raw else None
    if due_raw and due is None:
        raise ValidationError({'due_date': "Muddat YYYY-MM-DD ko'rinishida bo'lishi kerak"})
    if due and due < date:
        raise ValidationError({'due_date': "To'lash muddati sotuv sanasidan oldin bo'lishi mumkin emas"})
    try:
        paid_now = Decimal(str(data.get('paid_now') or '0'))
    except InvalidOperation:
        raise ValidationError({'paid_now': "Summa noto'g'ri"})
    if paid_now < 0:
        raise ValidationError({'paid_now': "Summa manfiy bo'lishi mumkin emas"})
    if paid_now >= total:
        raise ValidationError({'paid_now': "Oldindan to'langan summa jami summadan kam bo'lishi kerak. "
                                           "To'liq to'langan bo'lsa, \"Naqd\"ni tanlang."})
    return {'party_id': party_id, 'party_name': name, 'due_date': due, 'paid_now': paid_now}


def get_party(farm, kind, party_id=None, name=''):
    if party_id:
        if not str(party_id).isdigit():
            raise ValidationError({'party': "Noto'g'ri tanlov"})
        party = Party.objects.filter(pk=int(party_id), farm=farm, kind=kind).first()
        if party is None:
            raise ValidationError({'party': "Bu odam ro'yxatda topilmadi"})
        return party
    party = Party.objects.filter(farm=farm, kind=kind, name__iexact=name).first()
    return party or Party.objects.create(farm=farm, kind=kind, name=name[:120])


def add_payment(debt, amount, date, note, user):
    """Qarzga to'lov yozadi. Qarz balansga ta'sir qilsa, moliyada ham yozuv ochiladi."""
    finance_tx = None
    if debt.affects_balance:
        incoming = debt.party.kind == 'mijoz'
        description = f"Qarz to'lovi: {debt.party.name}"
        if debt.description:
            description += f" ({debt.description})"
        finance_tx = FinanceTransaction.objects.create(
            farm=debt.farm, transaction_type='kirim' if incoming else 'chiqim',
            category=debt.balance_category or ('sotuv' if incoming else 'boshqa'),
            amount=amount, description=description[:500], date=date, recorded_by=user)
    return DebtPayment.objects.create(
        debt=debt, amount=amount, date=date, note=note, recorded_by=user, finance_transaction=finance_tx)


def open_credit(*, farm, kind, credit, total, date, description, user, category,
                animal_group=None, animal_count=None):
    """Nasiya qarzini ochadi (va oldindan to'langan qismini yozadi)."""
    party = get_party(farm, kind, credit['party_id'], credit['party_name'])
    with transaction.atomic():
        debt = Debt.objects.create(
            farm=farm, party=party, amount=total, date=date, due_date=credit['due_date'],
            description=description[:200], recorded_by=user, affects_balance=True, balance_category=category,
            animal_group=animal_group, animal_count=animal_count)
        if credit['paid_now'] > 0:
            add_payment(debt, credit['paid_now'], date, "Oldindan to'langan", user)
    return debt


def update_payment_transaction(payment):
    """To'lov summasi/sanasi o'zgarsa, moliyadagi yozuv ham shunga moslanadi."""
    tx = payment.finance_transaction
    if tx is not None:
        tx.amount = payment.amount
        tx.date = payment.date
        tx.save(update_fields=['amount', 'date'])


def delete_payment(payment):
    tx = payment.finance_transaction
    payment.delete()
    if tx is not None:
        tx.delete()


def delete_debt(debt):
    """Qarzni to'liq o'chiradi: to'lovlarning moliyadagi yozuvlari ham o'chadi, nasiyaga sotilgan hayvonlar qaytadi."""
    from apps.animals.models import AnimalGroup
    with transaction.atomic():
        tx_ids = list(debt.payments.exclude(finance_transaction=None).values_list('finance_transaction_id', flat=True))
        if debt.animal_count and debt.animal_group_id:
            group = AnimalGroup.objects.select_for_update().get(pk=debt.animal_group_id)
            group.count += debt.animal_count
            if group.status == 'sotilgan':
                group.status = 'faol'
            group.save(update_fields=['count', 'status', 'updated_at'])
        debt.delete()
        FinanceTransaction.objects.filter(pk__in=tx_ids).delete()


def today():
    return timezone.localdate()
