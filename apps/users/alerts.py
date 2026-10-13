"""
Aqlli ogohlantirishlar: kunlik hisobotga qo'shiladigan bashorat va eslatmalar.

1. Yem bashorati  -- "yem 5 kunga yetadi" (so'nggi kunlardagi sarf asosida)
2. Chiqim ogohlantirishi -- "bu oy chiqim o'tgan oyning shu davridan 40% ko'p"
3. Vaksinatsiya eslatmasi -- muddati yaqinlashgan yoki o'tib ketgan vaksinatsiyalar

Har bir funksiya matn qatorlari ro'yxatini qaytaradi (ogohlantirish bo'lmasa -- bo'sh ro'yxat).
Chegaralarni shu fayl tepasidagi sozlamalardan o'zgartirish mumkin.
"""
import logging
import math
from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Sum
from django.utils import timezone

from apps.animals.models import AnimalEvent
from apps.finance.models import Transaction
from apps.inventory.models import InventoryItem, InventoryTransaction

logger = logging.getLogger(__name__)

MAX_ITEMS = 5  # har bir ro'yxatda ko'pi bilan nechta qator

# --- Yem bashorati ---
FEED_LOOKBACK_DAYS = 14   # sarf necha kunlik tarixdan hisoblanadi
FEED_MIN_DAYS = 3         # kamida necha kunlik kuzatuv bo'lishi kerak (yangi mahsulotda bashorat noto'g'ri chiqmasin)
FEED_MIN_RECORDS = 2      # kamida nechta sarf yozuvi bo'lishi kerak
FEED_WARN_DAYS = 7        # yem shu kundan kamga yetsa, ogohlantiriladi

# --- Chiqim ogohlantirishi ---
SPEND_GROWTH_PERCENT = 40            # o'tgan oydan necha foiz ko'p bo'lsa ogohlantirish
SPEND_MIN_DAY = 5                    # oyning birinchi kunlarida taqqoslash noaniq, shuning uchun kutamiz
SPEND_MIN_DIFF = Decimal('100000')   # farq shu summadan (so'm) kam bo'lsa, foiz katta bo'lsa ham xabar bermaymiz

# --- Vaksinatsiya ---
VACCINE_DAYS_AHEAD = 3     # necha kun oldindan eslatiladi
VACCINE_OVERDUE_DAYS = 7   # muddati o'tganlarni necha kungacha eslatamiz


def _money(value):
    return f"{Decimal(value or 0):,.0f}".replace(',', ' ')


def _qty(value):
    return format(Decimal(value).normalize(), 'f')


def _more(total):
    return [f"  ... va yana {total - MAX_ITEMS} ta"] if total > MAX_ITEMS else []


# ---------------------------------------------------------------- 1. Yem bashorati
def feed_forecast_lines(farm, today):
    items = list(InventoryItem.objects.filter(farm=farm, item_type='ozuqa'))
    if not items:
        return []

    since = today - timedelta(days=FEED_LOOKBACK_DAYS - 1)
    usage = {
        row['inventory_item']: row
        for row in InventoryTransaction.objects
        .filter(inventory_item_id__in=[i.id for i in items], transaction_type='sarf',
                date__gte=since, date__lte=today)
        .order_by()
        .values('inventory_item')
        .annotate(used=Sum('quantity'), n=Count('id'))
    }

    rows = []
    for item in items:
        row = usage.get(item.id)
        if not row or not row['used'] or row['n'] < FEED_MIN_RECORDS:
            continue
        # Mahsulot yaqinda qo'shilgan bo'lsa, kuzatuv kunlari faqat shu paytdan boshlab sanaladi
        start = max(since, timezone.localtime(item.created_at).date())
        observed_days = (today - start).days + 1
        if observed_days < FEED_MIN_DAYS:
            continue
        daily = row['used'] / observed_days
        if daily <= 0:
            continue
        days_left = item.quantity / daily
        if days_left <= FEED_WARN_DAYS:
            rows.append((days_left, item, daily))

    if not rows:
        return []
    rows.sort(key=lambda r: r[0])

    lines = [f"🌾 Yem bashorati: {len(rows)} ta"]
    for days_left, item, daily in rows[:MAX_ITEMS]:
        if item.quantity <= 0:
            left = "tugagan"
        elif days_left < 1:
            left = "1 kundan kam yetadi"
        else:
            left = f"~{math.floor(days_left)} kunga yetadi"
        lines.append(
            f"  • {item.item_name}: {left} "
            f"(qoldi {_qty(item.quantity)} {item.unit}, kuniga ~{_qty(daily.quantize(Decimal('0.1')))} {item.unit} ketmoqda)"
        )
    return lines + _more(len(rows))


# ---------------------------------------------------------------- 2. Chiqim ogohlantirishi
def _expense_by_category(farm, start, end):
    rows = (
        Transaction.objects
        .filter(farm=farm, transaction_type='chiqim', date__gte=start, date__lte=end)
        .order_by()
        .values('category')
        .annotate(s=Sum('amount'))
    )
    return {r['category']: (r['s'] or Decimal('0')) for r in rows}


def spending_alert_lines(farm, today):
    if today.day < SPEND_MIN_DAY:
        return []

    this_start = today.replace(day=1)
    prev_last = this_start - timedelta(days=1)
    prev_start = prev_last.replace(day=1)
    # O'tgan oyning xuddi shu davri bilan solishtiramiz (to'liq oy bilan emas): 1..bugungi kun
    prev_end = prev_start.replace(day=min(today.day, prev_last.day))

    current = _expense_by_category(farm, this_start, today)
    previous = _expense_by_category(farm, prev_start, prev_end)
    cur_total = sum(current.values(), Decimal('0'))
    prev_total = sum(previous.values(), Decimal('0'))
    if prev_total <= 0:
        return []  # solishtiradigan narsa yo'q

    diff = cur_total - prev_total
    percent = diff * 100 / prev_total
    if percent < SPEND_GROWTH_PERCENT or diff < SPEND_MIN_DIFF:
        return []

    lines = [
        f"📈 Bu oy chiqim o'tgan oyning shu davridan {percent:.0f}% ko'p: "
        f"{_money(cur_total)} so'm (o'tgan oy: {_money(prev_total)} so'm)"
    ]
    growth = {cat: amount - previous.get(cat, Decimal('0')) for cat, amount in current.items()}
    top = max(growth, key=growth.get) if growth else None
    if top and growth[top] > 0:
        name = dict(Transaction.CATEGORY_CHOICES).get(top, top)
        lines.append(f"  • Eng ko'p oshgani: {name} (+{_money(growth[top])} so'm)")
    return lines


# ---------------------------------------------------------------- 3. Vaksinatsiya eslatmasi
def _when(start_date, today):
    delta = (start_date - today).days
    if delta == 0:
        return "bugun"
    if delta == 1:
        return "ertaga"
    if delta > 1:
        return f"{delta} kundan keyin ({start_date:%d.%m})"
    return f"{-delta} kun kechikdi ({start_date:%d.%m})"


def vaccination_lines(farm, today):
    """
    Yakunlanmagan vaksinatsiya yozuvlari: sanasi yaqin kunlarda yoki yaqinda o'tib ketgan.
    Eslatma: "Ferma ishlari" bo'limida vaksinatsiya yozilganda boshlanish sanasi = vaksinatsiya sanasi,
    bajarilgach status "Yakunlangan" qilinadi -- shunda eslatma to'xtaydi.
    """
    events = list(
        AnimalEvent.objects.select_related('animal_group__animal_type')
        .filter(
            animal_group__farm=farm,
            animal_group__status='faol',
            event_type='vaksinatsiya',
            start_date__gte=today - timedelta(days=VACCINE_OVERDUE_DAYS),
            start_date__lte=today + timedelta(days=VACCINE_DAYS_AHEAD),
        )
        .exclude(status='yakunlangan')
        .order_by('start_date', 'id')
    )
    if not events:
        return []

    lines = [f"💉 Vaksinatsiya: {len(events)} ta"]
    for ev in events[:MAX_ITEMS]:
        lines.append(f"  • {ev.animal_group.animal_type.name}: {ev.title} — {_when(ev.start_date, today)}")
    return lines + _more(len(events))


# ---------------------------------------------------------------- Hammasi birga
def build_alert_lines(farm, today):
    """
    Fermaning barcha aqlli ogohlantirishlari. Birortasida xato chiqsa ham, kunlik hisobot
    to'xtab qolmasligi uchun xato log'ga yoziladi va qolganlari davom etadi.
    """
    lines = []
    for builder in (vaccination_lines, feed_forecast_lines, spending_alert_lines):
        try:
            lines += builder(farm, today)
        except Exception:
            logger.exception("Ogohlantirishni hisoblashda xato: %s (ferma id=%s)", builder.__name__, farm.pk)
    return lines
