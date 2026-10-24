"""
Ishchilarning oylik ish haqi: oy oxirida moliyaga avtomatik "Ish haqi" chiqimi yoziladi.

Qoidalar:
  * `Worker.monthly_salary` > 0 bo'lsa, har oyning oxirgi kuni (yoki undan keyin, server o'chiq bo'lgan bo'lsa) chiqim yoziladi;
  * hisob `salary_from` (oylik kiritilgan sana) va ishchi qo'shilgan sanadan boshlanadi: o'tgan oylar uchun chiqim yozilmaydi;
  * birinchi to'liq bo'lmagan oy kunlariga qarab hisoblanadi (masalan, oyning yarmidan boshlagan bo'lsa, yarim oylik);
  * (ishchi, oy) bo'yicha faqat bir marta yoziladi (`SalaryPayment`). Chiqimni o'chirsangiz, qayta yozilmaydi.
"""
import calendar
import logging
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import SalaryPayment, Worker

logger = logging.getLogger(__name__)


def month_end(first):
    return first.replace(day=calendar.monthrange(first.year, first.month)[1])


def _next_month(first):
    return date(first.year + (first.month == 12), first.month % 12 + 1, 1)


def start_date(worker):
    """Ish haqi hisoblanadigan eng birinchi kun."""
    joined = timezone.localtime(worker.joined_at).date() if worker.joined_at else None
    candidates = [d for d in (worker.salary_from, joined) if d is not None]
    return max(candidates) if candidates else None


def month_amount(worker, first, start):
    """Shu oy uchun summa: to'liq oy bo'lsa — oylik, boshlangan oy bo'lsa — kunlariga qarab."""
    end = month_end(first)
    period_start = max(start, first)
    days = (end - period_start).days + 1
    total = calendar.monthrange(first.year, first.month)[1]
    salary = Decimal(worker.monthly_salary)
    if days >= total:
        return salary.quantize(Decimal('1'), ROUND_HALF_UP)
    return (salary * days / total).quantize(Decimal('1'), ROUND_HALF_UP)


def due_months(worker, today):
    """Oxiri `today` dan oldin (yoki bugun) tugagan, hisoblanishi kerak bo'lgan oylar (oyning 1-kuni)."""
    start = start_date(worker)
    if start is None or Decimal(worker.monthly_salary or 0) <= 0:
        return []
    months, first = [], start.replace(day=1)
    while month_end(first) <= today:
        months.append(first)
        first = _next_month(first)
    return months


def _post_one(worker, first, start):
    """Bitta oy uchun chiqim yozadi. Allaqachon yozilgan bo'lsa, None qaytaradi."""
    from apps.finance.models import Transaction
    amount = month_amount(worker, first, start)
    if amount <= 0:
        return None
    try:
        with transaction.atomic():
            payment, created = SalaryPayment.objects.get_or_create(
                worker=worker, month=first, defaults={'amount': amount})
            if not created:
                return None
            name = worker.user.get_full_name() or worker.user.username
            payment.transaction = Transaction.objects.create(
                farm=worker.farm, transaction_type='chiqim', category='ish_haqi', amount=amount,
                date=month_end(first), recorded_by=worker.farm.owner,
                description=f"Ish haqi: {name} ({first:%Y-%m}), avtomatik",
            )
            payment.save(update_fields=['transaction'])
            return payment
    except IntegrityError:  # boshqa jarayon bir vaqtda yozib bo'ldi
        return None


def post_due(today=None, farm=None):
    """
    Tugagan oylar uchun hali yozilmagan ish haqini moliyaga chiqim qilib yozadi (qayta chaqirsa ham xavfsiz).
    Yangi yozilgan SalaryPayment'lar ro'yxatini qaytaradi va ferma egalariga Telegramdan xabar beradi.
    """
    today = today or timezone.localdate()
    workers = Worker.objects.select_related('user', 'farm__owner').filter(monthly_salary__gt=0)
    if farm is not None:
        workers = workers.filter(farm=farm)
    posted = []
    for worker in workers:
        start = start_date(worker)
        for first in due_months(worker, today):
            payment = _post_one(worker, first, start)
            if payment is not None:
                posted.append(payment)
    if posted:
        _notify(posted)
    return posted


def _notify(payments):
    from apps.users.digest import money
    from apps.users.notify import notify_users
    by_owner = {}
    for p in payments:
        by_owner.setdefault(p.worker.farm.owner_id, (p.worker.farm.owner, []))[1].append(p)
    for owner, items in by_owner.values():
        lines = ["💰 Ish haqi moliyaga chiqim qilib yozildi:"]
        for p in items[:10]:
            name = p.worker.user.get_full_name() or p.worker.user.username
            lines.append(f"  • {name} ({p.worker.farm.name}, {p.month:%m.%Y}) — {money(p.amount)} so'm")
        if len(items) > 10:
            lines.append(f"  ... va yana {len(items) - 10} ta")
        lines.append(f"Jami: {money(sum(p.amount for p in items))} so'm")
        lines.append("ℹ️ Pul berilmagan bo'lsa, «Moliya» bo'limida shu chiqimni o'chiring: qayta yozilmaydi.")
        try:
            notify_users([owner], "\n".join(lines))
        except Exception:
            logger.exception("Ish haqi xabarini yuborib bo'lmadi")


# Rejalashtiruvchi har daqiqa chaqirgani uchun, bazaga kuniga bir martagina murojaat qilamiz
_last_run = None


def post_due_once_a_day():
    global _last_run
    today = timezone.localdate()
    if _last_run == today:
        return []
    posted = post_due(today)
    _last_run = today
    return posted
