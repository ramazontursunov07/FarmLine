"""
Aqlli ogohlantirishlar: kunlik hisobotga qo'shiladigan bashorat va eslatmalar.

1. Yem bashorati  -- "yem 5 kunga yetadi": avvalo hayvonlar ehtiyoji (soni, vazni, suti) bo'yicha,
                     hisoblab bo'lmaganlari uchun so'nggi kunlardagi sarf asosida
2. Chiqim ogohlantirishi -- "bu oy chiqim o'tgan oyning shu davridan 40% ko'p"
3. Vaksinatsiya eslatmasi -- muddati yaqinlashgan yoki o'tib ketgan vaksinatsiyalar
4. Tug'ish eslatmasi -- tug'ishi yaqin yoki muddati o'tib ketgan bug'oz hayvonlar
5. Dori ushlab turish muddati -- davolangan hayvonlarning sutini/go'shtini hali sotib bo'lmaydi
6. Qarz eslatmasi -- muddati yaqinlashgan yoki o'tib ketgan nasiyalar (mijozlar va yetkazib beruvchilar)

Har bir funksiya matn qatorlari ro'yxatini qaytaradi (ogohlantirish bo'lmasa -- bo'sh ro'yxat).
Chegaralarni shu fayl tepasidagi sozlamalardan o'zgartirish mumkin.
"""
import logging
import math
from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Sum
from django.utils import timezone

from apps.animals.models import Animal, AnimalEvent
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

# Tug'ish eslatmasi
CALVING_DAYS_AHEAD = 14     # tug'ishga necha kun qolganda eslatma boshlanadi
CALVING_URGENT_DAYS = 3     # shu kundan kam qolsa, xabar "shoshilinch" belgisi (🚨) bilan chiqadi
CALVING_OVERDUE_DAYS = 21   # muddati o'tib ketganlarni necha kungacha eslatamiz

# Qarz eslatmasi: muddatiga shuncha kun qolganda boshlanadi, to'langunча har kuni eslatiladi
DEBT_DAYS_AHEAD = 3


def _money(value):
    return f"{Decimal(value or 0):,.0f}".replace(',', ' ')


def _qty(value):
    return format(Decimal(value).normalize(), 'f')


def _more(total):
    return [f"  ... va yana {total - MAX_ITEMS} ta"] if total > MAX_ITEMS else []


# ---------------------------------------------------------------- 1. Yem bashorati
def _kg_text(value):
    value = Decimal(value)
    if value >= 1000:
        return f"{(value / 1000).quantize(Decimal('0.1'))} tonna"
    return f"{value.quantize(Decimal('1'))} kg"


def feed_need_lines(farm, today):
    """
    Ehtiyojga asoslangan yem bashorati: hayvonlar soni, vazni va sutiga qarab kunlik ehtiyoj ombordagi zaxira bilan
    solishtiriladi. (satrlar, shu tur yemlar o'z ichiga olgan mahsulot id lari).
    """
    from apps.inventory import feed_need
    report = feed_need.build_report(farm, today)
    covered, rows = set(), []
    for k in report['kinds']:
        if Decimal(k['need_kg_per_day']) <= 0 or not k['has_items']:
            continue
        covered.update(i['id'] for i in k['items'])
        days = Decimal(k['days_left'])
        if days <= FEED_WARN_DAYS:
            rows.append((days, k))
    if not rows:
        return [], covered
    rows.sort(key=lambda r: r[0])
    lines = [f"🌾 Yem zaxirasi (hayvonlar ehtiyoji bo'yicha): {len(rows)} ta tur"]
    for days, k in rows:
        names = ", ".join(i['name'] for i in k['items'][:3])
        if Decimal(k['stock_kg']) <= 0:
            left = "tugagan"
        elif days < 1:
            left = "1 kundan kam yetadi"
        else:
            left = f"~{math.floor(days)} kunga yetadi"
        lines.append(
            f"  • {feed_need.KIND_LABELS[k['kind']].split(' (')[0]} ({names}): {left} "
            f"(omborda {_kg_text(k['stock_kg'])}, kuniga ~{_kg_text(k['need_kg_per_day'])} kerak)")
    return lines, covered


def feed_forecast_lines(farm, today):
    need_lines, covered = feed_need_lines(farm, today)
    return need_lines + _feed_history_lines(farm, today, skip_ids=covered)


def _feed_history_lines(farm, today, skip_ids=()):
    """O'tgan sarfga asoslangan bashorat: ehtiyoj bo'yicha hisoblab bo'lmagan mahsulotlar uchun."""
    items = list(InventoryItem.objects.filter(farm=farm, item_type='ozuqa').exclude(pk__in=skip_ids))
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

    this_start = today.replace(day=1) #oyning boshini topadi.
    prev_last = this_start - timedelta(days=1) #oyning oxirini topadi.
    prev_start = prev_last.replace(day=1) #o'tgan oyning birinchi kunini topadi.
    # O'tgan oyning xuddi shu davri bilan solishtiramiz (to'liq oy bilan emas): 1..bugungi kun
    prev_end = prev_start.replace(day=min(today.day, prev_last.day)) #o'tgan oydagi bugungi kunga teng sanani topadi.

    current = _expense_by_category(farm, this_start, today)
    previous = _expense_by_category(farm, prev_start, prev_end)
    cur_total = sum(current.values(), Decimal('0')) #shu oy chiqimi
    prev_total = sum(previous.values(), Decimal('0')) #o'tgan oy chiqimi
    if prev_total <= 0:
        return []  # solishtiradigan narsa yo'q

    diff = cur_total - prev_total #shu oy va o'tgan oy chiqimi farqi.
    percent = diff * 100 / prev_total #chiqimni necha foiz o'sganini hisoblaydi.
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
    if delta == 0: #Agarda vaksinatsiya bugun boshlangan bo'lsa.Bugun deydi.
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


# ---------------------------------------------------------------- 4. Tug'ish eslatmasi
def calving_lines(farm, today):
    """
    Tug'ishi yaqin (yoki muddati o'tib ketgan) bug'oz hayvonlar.
    Hayvon kartochkasida "Tug'ilish" yozilganda bug'ozlik tugaydi va eslatma o'zi to'xtaydi.
    """
    animals = list(
        Animal.objects.filter(
            farm=farm, status='faol', pregnant_since__isnull=False, due_date__isnull=False,
            due_date__gte=today - timedelta(days=CALVING_OVERDUE_DAYS),
            due_date__lte=today + timedelta(days=CALVING_DAYS_AHEAD),
        ).order_by('due_date', 'id')
    )
    if not animals:
        return []

    urgent = any(a.due_date <= today + timedelta(days=CALVING_URGENT_DAYS) for a in animals)
    lines = [f"{'🚨' if urgent else '🐄'} Tug'ishi yaqin: {len(animals)} ta"]
    for a in animals[:MAX_ITEMS]:
        lines.append(f"  • {a} — {_when(a.due_date, today)}")
    lines += _more(len(animals))
    if any(a.due_date <= today for a in animals):
        lines.append("  ℹ️ Tug'ib bo'lgan bo'lsa, hayvon kartochkasida «Tug'ilish» ni yozing: eslatma to'xtaydi.")
    return lines


# ---------------------------------------------------------------- 4b. Quritish va qayta urug'lantirish
def repro_lines(farm, today):
    """Sigirni quritish vaqti va tug'gandan keyin qayta urug'lantirish eslatmalari."""
    from apps.animals import repro
    rep = repro.build_report(farm, today)
    lines = []
    dry = rep['dry_off']
    if dry:
        urgent = any(r['status'] == 'vaqti' for r in dry)
        lines.append(f"{'🚨' if urgent else '🥛'} Quritish vaqti: {len(dry)} ta (tug'ishdan ~{repro.DRY_DAYS_BEFORE} kun oldin)")
        for r in dry[:MAX_ITEMS]:
            who = f"№{r['tag_number']}" + (f" {r['name']}" if r['name'] else '')
            lines.append(f"  • {who} — {_when(r['dry_date'], today)}, tug'ish {r['due_date']:%d.%m}")
        lines += _more(len(dry))
    rb = rep['rebreed']
    if rb:
        late = any(r['status'] == 'kechikdi' for r in rb)
        lines.append(f"{'⚠️' if late else '🐄'} Qayta urug'lantirish vaqti: {len(rb)} ta")
        for r in rb[:MAX_ITEMS]:
            who = f"№{r['tag_number']}" + (f" {r['name']}" if r['name'] else '')
            tail = (f", tug'ishlar orasi ~{r['projected_interval']} kun bo'ladi" if r['status'] == 'kechikdi' else '')
            lines.append(f"  • {who} — tug'gandan {r['days_since']} kun o'tdi{tail}")
        lines += _more(len(rb))
        lines.append("  ℹ️ Urug'lantirilgach, kartochkada bug'ozlik sanasini yozing: eslatma to'xtaydi.")
    return lines


# ---------------------------------------------------------------- Hammasi birga
# ---------------------------------------------------------------- 5. Dori ushlab turish muddati
def withdrawal_lines(farm, today):
    """Davolashdan keyin sut va go'shtni sotib bo'lmaydigan hayvonlar (qolgan kunlari bilan)."""
    from apps.animals.withdrawal import active_withdrawals
    rows = active_withdrawals(farm.pk, today)
    if not rows:
        return []
    lines = [f"⛔ Sut va go'shtni sotmang: {len(rows)} ta hayvon"]
    for r in rows[:MAX_ITEMS]:
        a = r['animal']
        who = f"№{a.tag_number}" + (f" {a.name}" if a.name else '')
        if r['until'] is None:
            when = "davolash davom etmoqda"
        elif r['days_left'] == 0:
            when = "bugun oxirgi kun, ertadan sotsa bo'ladi"
        else:
            when = f"{r['until']:%d.%m} gacha ({r['days_left']} kun qoldi)"
        lines.append(f"  • {who} — {r['medicine']}: {when}")
    return lines + _more(len(rows))


def debt_lines(farm, today):
    """
    Muddati yaqinlashgan yoki o'tib ketgan qarzlar: mijozlardan olinadigan va yetkazib beruvchilarga beriladigan.
    Qarz to'liq to'langach eslatma o'zi to'xtaydi. Mijoz bo'yicha jamlanadi: bir odamning bir necha qarzi bitta qator.
    """
    from apps.debts import stats

    horizon = today + timedelta(days=DEBT_DAYS_AHEAD)
    groups = {'mijoz': {}, 'taminotchi': {}}
    for d in stats.debts_with_paid(farm_id=farm.pk):
        left = stats.remaining(d)
        if left <= 0 or d.due_date is None or d.due_date > horizon:
            continue
        row = groups[d.party.kind].setdefault(d.party_id, {'name': d.party.name, 'left': Decimal('0'), 'due': d.due_date})
        row['left'] += left
        row['due'] = min(row['due'], d.due_date)  # eng erta muddat

    lines = []
    for kind, title in (('mijoz', "💳 Mijozlardan to'lov kutilmoqda"),
                        ('taminotchi', "💸 Yetkazib beruvchilarga to'lash kerak")):
        rows = sorted(groups[kind].values(), key=lambda r: (r['due'], r['name']))
        if not rows:
            continue
        total = sum((r['left'] for r in rows), Decimal('0'))
        lines.append(f"{title}: {len(rows)} ta, jami {_money(total)} so'm")
        for r in rows[:MAX_ITEMS]:
            lines.append(f"  • {r['name']} — {_money(r['left'])} so'm, {_when(r['due'], today)}")
        lines += _more(len(rows))
    return lines


def build_alert_lines(farm, today):
    """
    Fermaning barcha aqlli ogohlantirishlari. Birortasida xato chiqsa ham, kunlik hisobot
    to'xtab qolmasligi uchun xato log'ga yoziladi va qolganlari davom etadi.
    """
    lines = []
    for builder in (calving_lines, repro_lines, debt_lines, withdrawal_lines, vaccination_lines, feed_forecast_lines,
                    spending_alert_lines):
        try:
            lines += builder(farm, today)
        except Exception:
            logger.exception("Ogohlantirishni hisoblashda xato: %s (ferma id=%s)", builder.__name__, farm.pk)
    return lines

"""O'rganildi"""
