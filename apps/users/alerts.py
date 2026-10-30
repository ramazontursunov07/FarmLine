"""
Aqlli ogohlantirishlar: kunlik hisobotga qo'shiladigan bashorat va eslatmalar.

1. Yem bashorati  -- "yem 5 kunga yetadi": avvalo hayvonlar ehtiyoji (soni, vazni, suti) bo'yicha,
                     hisoblab bo'lmaganlari uchun so'nggi kunlardagi sarf asosida
2. Chiqim ogohlantirishi -- "bu oy chiqim o'tgan oyning shu davridan 40% ko'p"
3. Vaksinatsiya eslatmasi -- muddati yaqinlashgan yoki o'tib ketgan vaksinatsiyalar
4. Tug'ish eslatmasi -- tug'ishi yaqin yoki muddati o'tib ketgan bug'oz hayvonlar
5. Dori ushlab turish muddati -- davolangan hayvonlarning sutini/go'shtini hali sotib bo'lmaydi
6. Qarz eslatmasi -- muddati yaqinlashgan yoki o'tib ketgan nasiyalar (mijozlar va yetkazib beruvchilar)
7. Quritish eslatmasi -- tug'ishdan ~60 kun oldin sog'ishni to'xtatish vaqti (apps/animals/reproduction.py)
8. Qayta urug'lantirish -- tug'gandan keyin ~60 kundan boshlab; 117 kundan oshsa tug'ishlar orasi 400 kundan oshadi
9. Sut kamayishi -- sigir sutining oxirgi kunlarda keskin kamayishi (mastit yoki boshqa kasallikning birinchi belgisi bo'lishi mumkin)

Har bir funksiya matn qatorlari ro'yxatini qaytaradi (ogohlantirish bo'lmasa -- bo'sh ro'yxat).
Chegaralarni shu fayl tepasidagi sozlamalardan o'zgartirish mumkin.
"""
import logging
import math
from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Sum
from django.utils import timezone

from apps.animals.models import Animal, AnimalEvent, MilkRecord
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

# Quritish / qayta urug'lantirish (chegaralar apps/animals/reproduction.py da)
REBREED_NUDGE_DAYS = 7      # "urug'lantirish vaqti keldi" xabari ochilgan kundan necha kun davomida chiqadi

# Sut kamayishi: oxirgi kunlardagi o'rtacha sut oldingi o'rtachadan keskin kam bo'lsa ogohlantiriladi
MILK_DROP_PERCENT = 25                # necha foiz va undan ko'p kamaysa
MILK_DROP_MIN_LITERS = Decimal('2')   # kuniga kamida necha litr kamaysa (kam sutli sigirda foiz aldamasin)
MILK_RECENT_DAYS = 3                  # "oxirgi kunlar": kecha va undan oldingi 2 kun (bugun hali to'liq emas)
MILK_BASE_DAYS = 14                   # taqqoslash uchun oldingi necha kun
MILK_RECENT_MIN_RECORDS = 2           # oxirgi kunlarning kamida nechtasida sut yozilgan bo'lishi kerak
MILK_BASE_MIN_RECORDS = 5             # oldingi davrda kamida nechta kunlik yozuv bo'lishi kerak
MILK_BASE_MIN_LITERS = Decimal('5')   # kuniga shundan kam sut beradigan sigirlar kuzatilmaydi
MILK_NEAR_DRY_OFF_DAYS = 70           # tug'ishga shuncha kun qolgan bug'oz sigirda sut tabiiy kamayadi

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


def _repro_infos(farm, today):
    """[(hayvon, tsikl ma'lumoti)] -- faol urg'ochi qoramollar, bitta so'rov to'plami bilan."""
    from apps.animals import reproduction
    animals = list(Animal.objects.select_related('group__animal_type').filter(
        farm=farm, status='faol', sex='urgochi'))
    shared = reproduction.collect([a.pk for a in animals])
    out = []
    for a in animals:
        data = reproduction.info(a, today, shared['calvings'].get(a.pk, []), shared['milk'].get(a.pk))
        if data:
            out.append((a, data))
    return out


def dry_off_lines(farm, today):
    """Quritish vaqti: tug'ishdan ~60 kun oldin sog'ish to'xtatilishi kerak (keyingi laktatsiya sutini oshiradi)."""
    rows = [(a, d) for a, d in _repro_infos(farm, today) if d['dry_off_state'] in ('soon', 'now', 'late')]
    if not rows:
        return []
    rows.sort(key=lambda r: (r[1]['dry_off_date'], r[0].pk))
    late = any(d['dry_off_state'] == 'late' for _, d in rows)
    lines = [f"{'⚠️' if late else '🥛'} Quritish vaqti: {len(rows)} ta"]
    for a, d in rows[:MAX_ITEMS]:
        lines.append(f"  • {a} — {_when(d['dry_off_date'], today)}, tug'ish {a.due_date:%d.%m}")
    lines += _more(len(rows))
    lines.append("  ℹ️ Sog'ishni to'xtatgach, kartochkada «Quritildi» ni bosing: eslatma to'xtaydi.")
    return lines


def rebreed_lines(farm, today):
    """Tug'gan, hali bug'oz bo'lmagan sigirlar: urug'lantirish vaqti va tug'ishlar orasi muddati."""
    from apps.animals import reproduction as rp
    rows = []
    for a, d in _repro_infos(farm, today):
        state, days = d['rebreed_state'], d['days_since_calving']
        if state in ('late', 'critical') and days <= rp.REBREED_MAX_DAYS:
            rows.append((a, d))
        elif state == 'now' and days < rp.REBREED_FROM_DAYS + REBREED_NUDGE_DAYS:
            rows.append((a, d))
    if not rows:
        return []
    rows.sort(key=lambda r: (-r[1]['days_since_calving'], r[0].pk))
    critical = any(d['rebreed_state'] == 'critical' for _, d in rows)
    lines = [f"{'🚨' if critical else '🐄'} Urug'lantirish vaqti: {len(rows)} ta"]
    for a, d in rows[:MAX_ITEMS]:
        text = f"  • {a} — tug'gandan {d['days_since_calving']} kun"
        if d['rebreed_state'] == 'critical':
            text += f" (tug'ishlar orasi {rp.CALVING_INTERVAL_TARGET} kundan oshadi)"
        elif d['rebreed_state'] == 'late':
            text += f" ({d['conceive_by']:%d.%m} gacha bug'oz bo'lishi kerak)"
        lines.append(text)
    lines += _more(len(rows))
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


# ---------------------------------------------------------------- 9. Sut kamayishi
def milk_drop(totals, today):
    """
    totals -- {sana: shu kundagi jami litr}. Oxirgi kunlar o'rtachasi oldingi 14 kun o'rtachasidan keskin kam bo'lsa,
    (oldingi o'rtacha, oxirgi o'rtacha, kamayish foizi) qaytaradi, aks holda None. Bugun hisobga olinmaydi.
    """
    recent_days = [today - timedelta(days=i) for i in range(1, MILK_RECENT_DAYS + 1)]
    base_days = [today - timedelta(days=i) for i in range(MILK_RECENT_DAYS + 1, MILK_RECENT_DAYS + MILK_BASE_DAYS + 1)]
    recent = [totals[d] for d in recent_days if d in totals]
    base = [totals[d] for d in base_days if d in totals]
    if len(recent) < MILK_RECENT_MIN_RECORDS or len(base) < MILK_BASE_MIN_RECORDS:
        return None
    base_avg = sum(base, Decimal('0')) / len(base)
    recent_avg = sum(recent, Decimal('0')) / len(recent)
    if base_avg < MILK_BASE_MIN_LITERS:
        return None
    diff = base_avg - recent_avg
    percent = diff * 100 / base_avg
    if percent < MILK_DROP_PERCENT or diff < MILK_DROP_MIN_LITERS:
        return None
    return base_avg, recent_avg, percent


def milk_drop_lines(farm, today):
    """
    Sutini keskin kamaytirgan sigirlar. Kasallikni aniqlamaydi: faqat "tekshiring" deydi, sababi mastit,
    boshqa kasallik, yem yoki issiqlik bo'lishi mumkin. Quritilgan va tug'ishiga ~70 kun qolgan sigirlar
    hisobga olinmaydi (ularda sut tabiiy kamayadi).
    """
    since = today - timedelta(days=MILK_RECENT_DAYS + MILK_BASE_DAYS)
    rows = (
        MilkRecord.objects
        .filter(animal__farm=farm, animal__status='faol', animal__sex='urgochi', date__gte=since, date__lt=today)
        .order_by()
        .values('animal_id', 'date')
        .annotate(total=Sum('liters'))
    )
    by_animal = {}
    for r in rows:
        by_animal.setdefault(r['animal_id'], {})[r['date']] = r['total']
    if not by_animal:
        return []

    animals = {a.pk: a for a in Animal.objects.filter(pk__in=list(by_animal))}
    found = []
    for pk, totals in by_animal.items():
        a = animals.get(pk)
        if a is None or a.dried_off_on:
            continue
        if a.pregnant_since and a.due_date and (a.due_date - today).days <= MILK_NEAR_DRY_OFF_DAYS:
            continue
        result = milk_drop(totals, today)
        if result:
            found.append((a, *result))
    if not found:
        return []

    found.sort(key=lambda r: (-r[3], r[0].pk))
    lines = [f"📉 Sut kamaydi: {len(found)} ta"]
    for a, base, recent, percent in found[:MAX_ITEMS]:
        lines.append(f"  • {a} — kuniga {base:.1f} → {recent:.1f} l (−{percent:.0f}%)")
    lines += _more(len(found))
    lines.append("  ℹ️ Sababi turlicha bo'lishi mumkin (mastit, kasallik, yem, issiqlik): sigirni ko'zdan kechiring, "
                 "tuxum yoki yiringli sut, shish yoki isitma bo'lsa veterinarga ko'rsating.")
    return lines


def build_alert_lines(farm, today):
    """
    Fermaning barcha aqlli ogohlantirishlari. Birortasida xato chiqsa ham, kunlik hisobot
    to'xtab qolmasligi uchun xato log'ga yoziladi va qolganlari davom etadi.
    """
    lines = []
    for builder in (calving_lines, dry_off_lines, rebreed_lines, milk_drop_lines, debt_lines, withdrawal_lines,
                    vaccination_lines, feed_forecast_lines, spending_alert_lines):
        try:
            lines += builder(farm, today)
        except Exception:
            logger.exception("Ogohlantirishni hisoblashda xato: %s (ferma id=%s)", builder.__name__, farm.pk)
    return lines

"""O'rganildi"""
