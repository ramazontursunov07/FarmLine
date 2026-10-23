"""Kunlik hisobot matnlarini tuzish (Telegram uchun). Yuborish -- send_daily_digest buyrug'ida."""
import logging
from decimal import Decimal

from django.db.models import F, Q, Sum

from apps.animals.models import AnimalEvent
from apps.farms.models import Farm
from apps.finance.models import Transaction
from apps.inventory.models import InventoryItem
from apps.tasks.models import Task

from .alerts import build_alert_lines, calving_lines, dry_off_lines

logger = logging.getLogger(__name__)

MAX_ITEMS = 5  # har bir ro'yxatdan ko'pi bilan nechta qator ko'rsatiladi


def money(value):
    return f"{Decimal(value or 0):,.0f}".replace(',', ' ')


def qty(value):
    return format(value.normalize(), 'f')


def _more(total):
    return [f"  ... va yana {total - MAX_ITEMS} ta"] if total > MAX_ITEMS else []


def build_farm_section(farm, today):
    """Bitta fermaning ahvoli. Muhim narsa bo'lmasa ham kirim-chiqim qatori chiqadi."""
    lines = [f"🏡 {farm.name}"]

    day = Transaction.objects.filter(farm=farm, date=today)
    income = day.filter(transaction_type='kirim').aggregate(s=Sum('amount'))['s']
    expense = day.filter(transaction_type='chiqim').aggregate(s=Sum('amount'))['s']
    lines.append(f"💰 Bugun: kirim {money(income)}, chiqim {money(expense)} so'm")

    treatments = list(
        AnimalEvent.objects.select_related('animal_group__animal_type')
        .filter(animal_group__farm=farm, event_type__in=('kasallik', 'davolash'))
        .exclude(status='yakunlangan')
        .order_by('start_date')
    )
    if treatments:
        lines.append(f"🩺 Davolanayotganlar: {len(treatments)} ta")
        for ev in treatments[:MAX_ITEMS]:
            lines.append(f"  • {ev.animal_group.animal_type.name}: {ev.title} — {ev.days_since_start} kun")
        lines += _more(len(treatments))

    low = list(
        InventoryItem.objects.filter(farm=farm, quantity__lte=F('low_stock_threshold')).order_by('item_name')
    )
    if low:
        lines.append(f"📦 Omborda kam qolgan: {len(low)} ta")
        for it in low[:MAX_ITEMS]:
            lines.append(f"  • {it.item_name}: {qty(it.quantity)} {it.unit}")
        lines += _more(len(low))

    overdue = Task.objects.filter(farm=farm, due_date__lt=today).exclude(status='bajarildi').count()
    if overdue:
        lines.append(f"⏰ Muddati o'tgan vazifalar: {overdue} ta")

    lines += build_alert_lines(farm, today)  # aqlli ogohlantirishlar (apps/users/alerts.py)

    return "\n".join(lines)


def build_owner_digest(owner, today):
    farms = Farm.objects.filter(owner=owner).order_by('name')
    if not farms:
        return None
    sections = [build_farm_section(f, today) for f in farms]
    return f"📊 FarmLine — kunlik hisobot ({today:%d.%m.%Y})\n\n" + "\n\n".join(sections)


def _worker_calving_lines(user, today):
    """Ishchi ishlaydigan fermalardagi tug'ishi yaqin va quritilishi kerak hayvonlar."""
    lines = []
    for farm in Farm.objects.filter(workers__user=user).distinct().order_by('name'):
        farm_lines = []
        for builder in (calving_lines, dry_off_lines):
            try:
                farm_lines += builder(farm, today)
            except Exception:
                logger.exception("Ishchi hisobotida xato: %s", builder.__name__)
        if farm_lines:
            lines += [f"🏡 {farm.name}"] + farm_lines
    return lines


def build_worker_digest(user, today):
    """Ishchining ochiq vazifalari va tug'ishi yaqin hayvonlar. Ikkalasi ham bo'lmasa None (xabar yuborilmaydi)."""
    tasks = list(
        Task.objects.select_related('farm')
        .filter(farm__workers__user=user)
        .filter(Q(assigned_to=user) | Q(assigned_to__isnull=True))
        .exclude(status='bajarildi')
        .distinct()
        .order_by('due_date', '-id')
    )
    calving = _worker_calving_lines(user, today)
    if not tasks and not calving:
        return None

    lines = []
    if tasks:
        lines.append(f"📋 FarmLine — bugungi vazifalaringiz ({today:%d.%m.%Y}): {len(tasks)} ta")
        for t in tasks[:MAX_ITEMS * 2]:
            mark = "⏰ " if t.due_date and t.due_date < today else "• "
            due = f" (muddat: {t.due_date:%d.%m})" if t.due_date else ""
            lines.append(f"{mark}{t.title}{due}")
        lines += _more(len(tasks)) if len(tasks) > MAX_ITEMS * 2 else []
    if calving:
        if tasks:
            lines.append("")
        else:
            lines.append(f"📋 FarmLine — bugungi eslatmalar ({today:%d.%m.%Y})")
        lines += calving
    return "\n".join(lines)


"""O'rganildi."""
