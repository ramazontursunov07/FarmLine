"""AI yordamchiga beriladigan foydalanuvchi ma'lumoti (ferma holati).

Maxfiylik: fermer o'z fermalarini to'liq ko'radi; ishchi faqat o'z vazifalarini va sut miqdorini
(pulsiz) ko'radi; admin uchun hech narsa berilmaydi.
Hajm cheklangan: har bir ro'yxatdan eng ko'pi bilan MAX_ROWS ta qator olinadi.

AI faqat shu matndagi raqamlarga tayanadi, shuning uchun fermerlar ko'p so'raydigan narsalar
(sut ombori, kirim-chiqim: kecha/hafta/oy/yil, oylar va kunlar kesimi, qarzlar) shu yerda tayyor turadi.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Q, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone

from apps.animals.models import AnimalEvent, AnimalGroup, MilkRecord, MilkSale
from apps.animals.views import milk_balance
from apps.animals.withdrawal import withheld_liters
from apps.debts import stats as debt_stats
from apps.farms.models import Farm
from apps.finance.models import Transaction
from apps.inventory.models import InventoryItem
from apps.tasks.models import Task
from apps.users.digest import build_worker_digest, money, qty
from apps.weather.services import farm_weather_context

MAX_FARMS = 5
MAX_ROWS = 10


def _period(farm, start, end):
    row = Transaction.objects.filter(farm=farm, date__gte=start, date__lte=end).aggregate(
        income=Sum('amount', filter=Q(transaction_type='kirim')),
        expense=Sum('amount', filter=Q(transaction_type='chiqim')),
    )
    income, expense = row['income'] or 0, row['expense'] or 0
    return income, expense, income - expense


WEEKDAYS = ('dushanba', 'seshanba', 'chorshanba', 'payshanba', 'juma', 'shanba', 'yakshanba')
MONTHS_BACK = 5  # shu oy bilan birga oxirgi 6 oy kesimi
DAYS_BACK = 6  # bugun bilan birga oxirgi 7 kun


def _month_start(day, back=0):
    """`day` dan `back` oy oldingi oyning 1-kuni."""
    index = day.year * 12 + (day.month - 1) - back
    return date(index // 12, index % 12 + 1, 1)


def _milk_between(farm, start, end):
    total = MilkRecord.objects.filter(animal__farm=farm, date__gte=start, date__lte=end).aggregate(
        t=Sum('liters'))['t']
    return total or Decimal('0')


def _milk_lines(farm, today, with_money, tag=''):
    """Sut ombori (qolgan, sotilgan, dori ta'sirida) va sog'ilgan sut davrlar bo'yicha."""
    produced, sold = milk_balance(farm.pk)
    where = f" ({tag})" if tag else ''
    if produced <= 0 and sold <= 0:
        return [f"Sut ombori{where}: hali sog'ilgan sut kiritilmagan"]

    available = max(produced - sold, Decimal('0'))
    withheld = min(withheld_liters(farm.pk, today), available)
    head = (f"Sut ombori{where}: omborda {qty(available)} l sut qolgan "
            f"(jami sog'ilgan {qty(produced)} l, sotilgan {qty(sold)} l)")
    if withheld > 0:
        head += (f"; shundan {qty(withheld)} l dori ushlab turish muddatida (sotib bo'lmaydi), "
                 f"sotsa bo'ladigani {qty(max(available - withheld, Decimal('0')))} l")
    lines = [head]

    yesterday = today - timedelta(days=1)
    week_start = today - timedelta(days=DAYS_BACK)
    month_start = today.replace(day=1)
    lines.append(
        "Sog'ilgan sut: "
        f"bugun {qty(_milk_between(farm, today, today))} l, "
        f"kecha {qty(_milk_between(farm, yesterday, yesterday))} l, "
        f"oxirgi 7 kun {qty(_milk_between(farm, week_start, today))} l, "
        f"shu oy {qty(_milk_between(farm, month_start, today))} l"
    )
    if with_money:
        row = MilkSale.objects.filter(farm=farm, date__gte=month_start, date__lte=today).aggregate(
            liters=Sum('liters'), amount=Sum('amount'))
        if row['liters']:
            lines.append(f"Sotilgan sut shu oy: {qty(row['liters'])} l, sotuv summasi {money(row['amount'])} so'm")
    return lines


def _daily_lines(farm, today, with_money):
    """Oxirgi 7 kun: har bir kun uchun sog'ilgan sut va (fermer uchun) kirim-chiqim. Bo'sh kunlar tushiriladi."""
    start = today - timedelta(days=DAYS_BACK)
    milk = {
        r['date']: r['liters']
        for r in MilkRecord.objects.filter(animal__farm=farm, date__gte=start, date__lte=today)
        .values('date').annotate(liters=Sum('liters')).order_by()
    }
    fin = {}
    if with_money:
        fin = {
            r['date']: r
            for r in Transaction.objects.filter(farm=farm, date__gte=start, date__lte=today)
            .values('date').annotate(
                income=Sum('amount', filter=Q(transaction_type='kirim')),
                expense=Sum('amount', filter=Q(transaction_type='chiqim')),
            ).order_by()
        }
    lines = []
    for i in range(DAYS_BACK + 1):
        day = today - timedelta(days=i)
        parts = []
        if milk.get(day):
            parts.append(f"sut {qty(milk[day])} l")
        if fin.get(day):
            parts.append(f"kirim {money(fin[day]['income'])}, chiqim {money(fin[day]['expense'])}")
        if parts:
            lines.append(f"  • {day:%d.%m} ({WEEKDAYS[day.weekday()]}): " + ", ".join(parts))
    return ["Kunlar bo'yicha (oxirgi 7 kun, bo'sh kunlar yo'q):"] + lines if lines else []


def _monthly_lines(farm, today):
    """Oxirgi 6 oy: har oyning kirim-chiqimi (bo'sh oylar tushiriladi)."""
    rows = (
        Transaction.objects.filter(farm=farm, date__gte=_month_start(today, MONTHS_BACK))
        .annotate(month=TruncMonth('date')).values('month')
        .annotate(income=Sum('amount', filter=Q(transaction_type='kirim')),
                  expense=Sum('amount', filter=Q(transaction_type='chiqim')))
        .order_by('month')
    )
    lines = [f"  • {r['month']:%Y-%m}: kirim {money(r['income'])}, chiqim {money(r['expense'])}"
             for r in rows if r['income'] or r['expense']]
    return ["Oylar bo'yicha (oxirgi 6 oy):"] + lines if lines else []


def _debt_lines(farm, today):
    """Qarzlar: kim fermerga qarzdor, fermer kimga qarzdor (qoldiq va muddati o'tganlari)."""
    debts = list(debt_stats.debts_with_paid(farm_id=farm.pk))
    if not debts:
        return ["Qarzlar: kiritilmagan"]
    lines = []
    groups = (
        ("Sizga qarzdorlar (mijozlar)", [d for d in debts if d.party.kind == 'mijoz']),
        ("Siz qarzdorsiz (yetkazib beruvchilarga)", [d for d in debts if d.party.kind == 'taminotchi']),
    )
    for label, items in groups:
        t = debt_stats.totals(items, today)
        if not t['open_count']:
            lines.append(f"{label}: ochiq qarz yo'q")
            continue
        text = f"{label}: jami qoldiq {money(t['remaining'])} so'm ({t['open_count']} ta qarz)"
        if t['overdue_count']:
            text += f", shundan muddati o'tgan {money(t['overdue_amount'])} so'm ({t['overdue_count']} ta)"
        lines.append(text)

        people = {}
        for d in items:
            left = debt_stats.remaining(d)
            if left <= 0:
                continue
            row = people.setdefault(d.party_id, {'name': d.party.name, 'left': Decimal('0'),
                                                 'due': None, 'overdue': False})
            row['left'] += left
            if d.due_date and (row['due'] is None or d.due_date < row['due']):
                row['due'] = d.due_date
            if debt_stats.is_overdue(d, today):
                row['overdue'] = True
        for row in sorted(people.values(), key=lambda r: r['left'], reverse=True)[:5]:
            if row['overdue']:
                extra = ", MUDDATI O'TGAN"
            elif row['due']:
                extra = f", muddat {row['due']:%d.%m.%Y}"
            else:
                extra = ''
            lines.append(f"  • {row['name']}: {money(row['left'])} so'm{extra}")
    return lines


def _farm_context(farm, today):
    month_start = today.replace(day=1)
    prev_end = month_start - timedelta(days=1)
    prev_start = prev_end.replace(day=1)

    lines = [f"=== Ferma: {farm.name} ({farm.get_farm_type_display()}, {farm.location}) ==="]

    # Hayvonlar
    animals = (
        AnimalGroup.objects.filter(farm=farm, status='faol')
        .values('animal_type__name', 'breed')
        .annotate(total=Sum('count'))
        .order_by('-total')[:MAX_ROWS]
    )
    if animals:
        lines.append("Hayvonlar (faol): " + ", ".join(
            f"{a['animal_type__name']}{' (' + a['breed'] + ')' if a['breed'] else ''} — {a['total']} ta"
            for a in animals
        ))
    else:
        lines.append("Hayvonlar: kiritilmagan")

    # Sut (ombor va sog'ilgan miqdor)
    lines += _milk_lines(farm, today, with_money=True)

    # Moliya: haqiqiy to'langan pul bo'yicha
    yesterday = today - timedelta(days=1)
    week_start = today - timedelta(days=DAYS_BACK)
    year_start = today.replace(month=1, day=1)
    for label, (start, end) in (
        ("Bugun", (today, today)),
        ("Kecha", (yesterday, yesterday)),
        (f"Oxirgi 7 kun ({week_start:%d.%m}–{today:%d.%m})", (week_start, today)),
        (f"Shu oy ({month_start:%d.%m}–{today:%d.%m})", (month_start, today)),
        ("O'tgan oy", (prev_start, prev_end)),
        (f"Shu yil ({today.year})", (year_start, today)),
    ):
        inc, exp, profit = _period(farm, start, end)
        word = "foyda" if profit >= 0 else "zarar"
        lines.append(f"{label}: kirim {money(inc)}, chiqim {money(exp)}, {word} {money(abs(profit))} so'm")
    lines.append("(Kirim-chiqim haqiqiy olingan/to'langan pul bo'yicha; nasiyaga berilgan va hali to'lanmagan pul "
                 "kirimda emas, quyidagi qarzlarda.)")
    lines += _monthly_lines(farm, today)
    lines += _daily_lines(farm, today, with_money=True)

    names = dict(Transaction.CATEGORY_CHOICES)
    top = (
        Transaction.objects.filter(farm=farm, transaction_type='chiqim', date__gte=month_start)
        .values('category').annotate(total=Sum('amount')).order_by('-total')[:5]
    )
    if top:
        lines.append("Shu oy eng katta chiqimlar: " + ", ".join(
            f"{names.get(t['category'], t['category'])} {money(t['total'])}" for t in top
        ))
    top_in = (
        Transaction.objects.filter(farm=farm, transaction_type='kirim', date__gte=month_start)
        .values('category').annotate(total=Sum('amount')).order_by('-total')[:5]
    )
    if top_in:
        lines.append("Shu oy kirim manbalari: " + ", ".join(
            f"{names.get(t['category'], t['category'])} {money(t['total'])}" for t in top_in
        ))

    recent = Transaction.objects.filter(farm=farm).order_by('-date', '-id')[:5]
    if recent:
        lines.append("Oxirgi kirim-chiqimlar:")
        for t in recent:
            lines.append(
                f"  • {t.date:%d.%m.%Y} {t.get_transaction_type_display()} {money(t.amount)} so'm "
                f"({t.get_category_display()}){': ' + t.description[:60] if t.description else ''}"
            )

    # Qarzlar (nasiya)
    lines += _debt_lines(farm, today)

    # Ombor
    items = list(InventoryItem.objects.filter(farm=farm).order_by('item_name')[:MAX_ROWS * 2])
    if items:
        lines.append("Ombor:")
        for it in items:
            low = " (KAM QOLGAN!)" if it.quantity <= it.low_stock_threshold else ""
            lines.append(f"  • {it.item_name}: {qty(it.quantity)} {it.unit}{low}")

    # Davolanayotgan hayvonlar
    sick = list(
        AnimalEvent.objects.select_related('animal_group__animal_type')
        .filter(animal_group__farm=farm, event_type__in=('kasallik', 'davolash'))
        .exclude(status='yakunlangan').order_by('start_date')[:MAX_ROWS]
    )
    if sick:
        lines.append("Davolanayotganlar:")
        for ev in sick:
            lines.append(f"  • {ev.animal_group.animal_type.name}: {ev.title} ({ev.days_since_start} kun)")

    # Vazifalar va ishchilar
    open_tasks = Task.objects.filter(farm=farm).exclude(status='bajarildi')
    overdue = open_tasks.filter(due_date__lt=today).count()
    lines.append(f"Ochiq vazifalar: {open_tasks.count()} ta (shundan muddati o'tgan: {overdue} ta)")
    for t in open_tasks.order_by('due_date', '-id')[:5]:
        due = f", muddat {t.due_date:%d.%m}" if t.due_date else ""
        lines.append(f"  • {t.title}{due}")
    workers = farm.workers.select_related('user').all()[:MAX_ROWS]
    if workers:
        lines.append("Ishchilar: " + ", ".join(w.user.get_full_name() or w.user.username for w in workers))

    return "\n".join(lines)


def build_context(user, today=None):
    today = today or timezone.localdate()
    if user.role == 'fermer':
        farms = Farm.objects.filter(owner=user).order_by('name')[:MAX_FARMS]
        parts = [_farm_context(f, today) for f in farms]
        # Ob-havo faqat birinchi fermaga (tez ishlashi uchun; natija 30 daqiqa saqlanadi)
        weather = farm_weather_context(farms[0]) if farms else None
        return "\n\n".join(parts + ([weather] if weather else []))
    if user.role == 'ishchi':
        text = build_worker_digest(user, today) or ''
        profile = user.worker_profiles.select_related('farm').first()
        weather = farm_weather_context(profile.farm) if profile else None
        # Ishchi sut miqdorini ko'ra oladi (pul ma'lumotisiz)
        profiles = list(user.worker_profiles.select_related('farm')[:MAX_FARMS])
        milk = []
        for p in profiles:
            milk += _milk_lines(p.farm, today, with_money=False, tag=p.farm.name)
            milk += _daily_lines(p.farm, today, with_money=False)
        return "\n\n".join(p for p in (text, "\n".join(milk), weather) if p)
    return ''
