"""
Yem ehtiyoji: guruhdagi hayvonlar, ularning vazni va sutiga qarab "kuniga qancha yem kerak" ni hisoblab,
ombordagi zaxira bilan solishtiradi (o'tgan sarfga emas, haqiqiy ehtiyojga tayanadi).

Me'yorlar knowledge/yem_ratsion/yem_ratsion.md dagi taxminiy ko'rsatkichlardan olingan (vazni ~550 kg sigir):
  - sutdorlik ~11 l:  pichan 4,5 / silos 13,5 / konsentrat 2,5 kg
  - sutdorlik ~20 l:  pichan 5,5 / silos 22,5 / konsentrat ~6 kg
  - quruq davr:       pichan ~7 / silos ~10 / konsentrat 1,5 kg
Bular taxminiy: aniq ratsion nasl, yem sifati va mavsumga bog'liq (zootexnik bilan kelishing).
Yem 3 turga bo'linadi: dag'al (pichan, beda, somon), shirali (silos, yashil o't), konsentrat (omuxta, kepak, arpa...).
"""
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from apps.animals.models import Animal, AnimalGroup, MilkRecord, WeightRecord

from .models import InventoryItem, InventoryTransaction

KINDS = ('dagal', 'shirali', 'konsentrat')
KIND_LABELS = {
    'dagal': "Dag'al yem (pichan, beda, somon)",
    'shirali': "Shirali yem (silos, yashil o't)",
    'konsentrat': "Konsentrat (omuxta, kepak, arpa, makkajo'xori)",
}
SKIP = 'hisobsiz'  # yem turi: hisobga olinmasin (masalan, tuz, premiks)

REFERENCE_WEIGHT = 550   # kg: me'yorlar shu vazndagi sigir uchun
WEIGHT_FACTOR = (Decimal('0.7'), Decimal('1.3'))
MILK_LOOKBACK_DAYS = 14  # shu kunlarda sut yozilgan bo'lsa, sigir sutli hisoblanadi
ASSUMED_LITERS = Decimal('11')  # kartochkasi yo'q sigirlar uchun taxminiy sutdorlik
ADULT_DAYS, CALF_DAYS = 365, 90
USE_LOOKBACK_DAYS = 14   # haqiqiy sarf shuncha kundan hisoblanadi
USE_MIN_DAYS, USE_MIN_RECORDS = 3, 2

TO_KG = {
    'kg': Decimal(1), 'kilogram': Decimal(1), 'kilo': Decimal(1),
    'tonna': Decimal(1000), 't': Decimal(1000), 'tn': Decimal(1000),
    'g': Decimal('0.001'), 'gr': Decimal('0.001'), 'gram': Decimal('0.001'),
}

# Nom bo'yicha avtomatik aniqlash (apostroflar olib tashlangan, kichik harf). Tartib muhim: aniqroq turlar oldin.
KEYWORDS = (
    ('shirali', ('silos', 'senaj', 'yashil', 'lavlagi', 'sabzi', 'qovoq')),
    ('dagal', ('pichan', 'beda', 'somon', 'xashak', 'pichen')),
    ('konsentrat', ('omuxta', 'kepak', 'arpa', 'makka', 'bugdoy', 'kunjara', 'shrot', 'konsentrat',
                    'starter', 'kombikorm', 'jmix', 'yem', 'don')),
)

_APOS = str.maketrans({c: '' for c in "'ʻʼ‘’`´"})


def detect_kind(name):
    text = str(name or '').lower().translate(_APOS)
    for kind, words in KEYWORDS:
        if any(w in text for w in words):
            return kind
    return None


def item_kind(item):
    if item.feed_kind:
        return None if item.feed_kind == SKIP else item.feed_kind
    return detect_kind(item.item_name)


def item_kg(item):
    """Mahsulot zaxirasini kg ga o'giradi. (kg yoki None)."""
    factor = TO_KG.get(str(item.unit or '').strip().lower().rstrip('.'))
    if factor is None:
        factor = item.kg_per_unit
    return None if factor is None else Decimal(item.quantity) * Decimal(factor)


def _clamp(value, low, high):
    return max(low, min(high, value))


def dairy_ration(liters):
    """Sutli sigirning kunlik ratsioni (kg), vazni ~550 kg bo'lganda."""
    l = Decimal(liters)
    return {
        'dagal': _clamp(Decimal('4.5') + (l - 11) * Decimal('0.11'), Decimal(4), Decimal(6)),
        'shirali': _clamp(Decimal('13.5') + (l - 11), Decimal(10), Decimal(25)),
        'konsentrat': _clamp(Decimal('2.5') + (l - 11) * Decimal('0.4'), Decimal('1.5'), Decimal(9)),
    }


RATIONS = {
    'quruq': ('Quruq davrdagi sigir', {'dagal': Decimal(7), 'shirali': Decimal(10), 'konsentrat': Decimal('1.5')}, True),
    'saqlovchi': ('Katta hayvon (sut bermaydi)',
                  {'dagal': Decimal(6), 'shirali': Decimal(12), 'konsentrat': Decimal('1.5')}, True),
    'yosh': ('Yosh mol (3-12 oy)', {'dagal': Decimal('2.5'), 'shirali': Decimal(5), 'konsentrat': Decimal('1.5')}, False),
    'buzoq': ('Buzoq (3 oygacha)', {'dagal': Decimal('0.3'), 'shirali': Decimal(0), 'konsentrat': Decimal('0.8')}, False),
    'qoy_echki': ("Qo'y / echki", {'dagal': Decimal('1.5'), 'shirali': Decimal(0), 'konsentrat': Decimal('0.3')}, False),
    'parranda': ('Parranda', {'dagal': Decimal(0), 'shirali': Decimal(0), 'konsentrat': Decimal('0.115')}, False),
}


def species(type_name):
    name = str(type_name or '').lower().translate(_APOS)
    if any(w in name for w in ('sigir', 'qoramol', 'buzoq', 'buqa', 'mol')):
        return 'qoramol'
    if any(w in name for w in ('qoy', 'echki', 'uloq', 'qochqor')):
        return 'qoy_echki'
    if any(w in name for w in ('tovuq', 'parranda', 'broyler', 'juja', 'kurka', 'ordak', 'goz')):
        return 'parranda'
    return None


def _factor(weight):
    if not weight:
        return Decimal(1)
    return _clamp(Decimal(weight) / REFERENCE_WEIGHT, *WEIGHT_FACTOR)


def _add(total, ration, count=1, factor=Decimal(1)):
    for kind in KINDS:
        total[kind] += ration.get(kind, Decimal(0)) * count * factor


def compute_needs(farm, today):
    """Hayvonlar bo'yicha kunlik ehtiyoj. (kind -> kg/kun, toifalar jadvali, ogohlantirishlar)."""
    need = {k: Decimal(0) for k in KINDS}
    rows = defaultdict(lambda: {'count': 0, 'per_head': None, 'note': ''})
    warnings = []

    groups = list(AnimalGroup.objects.filter(farm=farm, status='faol').select_related('animal_type'))
    cards = list(Animal.objects.filter(farm=farm, status='faol', group__status='faol')
                 .select_related('group__animal_type'))
    since = today - timedelta(days=MILK_LOOKBACK_DAYS - 1)

    # So'nggi vazn va so'nggi kunlardagi o'rtacha sut
    weights = {}
    for animal_id, kg in WeightRecord.objects.filter(animal__in=cards).order_by('date', 'id').values_list(
            'animal_id', 'weight_kg'):
        weights[animal_id] = kg
    milk = defaultdict(lambda: [Decimal(0), set()])
    for animal_id, day, liters in MilkRecord.objects.filter(
            animal__in=cards, date__gte=since, date__lte=today).values_list('animal_id', 'date', 'liters'):
        milk[animal_id][0] += liters
        milk[animal_id][1].add(day)

    cards_per_group = defaultdict(int)
    no_weight = 0
    unsupported = set()
    for a in cards:
        cards_per_group[a.group_id] += 1
        kind_species = species(a.group.animal_type.name)
        if kind_species is None:
            unsupported.add(a.group.animal_type.name)
            continue
        if kind_species in ('qoy_echki', 'parranda'):
            key = kind_species
            _add(need, RATIONS[key][1])
            rows[key]['count'] += 1
            continue

        age = (today - a.birth_date).days if a.birth_date else None
        weight = weights.get(a.pk)
        if a.sex == 'urgochi' and (age is None or age >= ADULT_DAYS) and a.pk in milk:
            total, days = milk[a.pk]
            liters = total / len(days)
            ration = dairy_ration(liters)
            _add(need, ration, factor=_factor(weight))
            rows['sutli']['count'] += 1
            rows['sutli']['sum_l'] = rows['sutli'].get('sum_l', Decimal(0)) + liters
            if weight is None:
                no_weight += 1
            continue
        if age is not None and age < CALF_DAYS:
            key = 'buzoq'
        elif age is not None and age < ADULT_DAYS:
            key = 'yosh'
        elif a.sex == 'urgochi' and a.pregnant_since is not None:
            key = 'quruq'
        else:
            key = 'saqlovchi'
        _add(need, RATIONS[key][1], factor=_factor(weight) if RATIONS[key][2] else Decimal(1))
        rows[key]['count'] += 1
        if RATIONS[key][2] and weight is None:
            no_weight += 1

    # Kartochkasi ochilmagan hayvonlar: guruh sonidan faol kartochkalar ayiriladi
    assumed = 0
    for g in groups:
        rest = g.count - cards_per_group.get(g.pk, 0)
        if rest <= 0:
            continue
        kind_species = species(g.animal_type.name)
        if kind_species is None:
            unsupported.add(g.animal_type.name)
            continue
        if kind_species in ('qoy_echki', 'parranda'):
            _add(need, RATIONS[kind_species][1], count=rest)
            rows[kind_species]['count'] += rest
            continue
        # Qoramol: nima ekani noma'lum, shuning uchun o'rtacha sutli sigir deb olinadi (taxmin)
        _add(need, dairy_ration(ASSUMED_LITERS), count=rest)
        rows['kartochkasiz']['count'] += rest
        assumed += rest

    if assumed:
        warnings.append(
            f"{assumed} ta hayvonning kartochkasi ochilmagan: ular o'rtacha sutli sigir (~{ASSUMED_LITERS} l) deb "
            "taxmin qilindi. Kartochka ochib vazn va sutni yozsangiz, hisob aniqlashadi.")
    if no_weight:
        warnings.append(f"{no_weight} ta katta hayvonning vazni yozilmagan: o'rtacha vazn (550 kg) olindi.")
    if unsupported:
        warnings.append("Bu turlar uchun me'yor yo'q (hisobga olinmadi): " + ", ".join(sorted(unsupported)))

    table = []
    labels = {'sutli': 'Sutli sigir', 'kartochkasiz': "Kartochkasiz qoramol (taxmin: sutli sigir)"}
    for key, row in rows.items():
        if not row['count']:
            continue
        if key == 'sutli':
            avg = row['sum_l'] / row['count']
            ration, label = dairy_ration(avg), f"Sutli sigir (o'rtacha {avg.quantize(Decimal('0.1'))} l/kun)"
        elif key == 'kartochkasiz':
            ration, label = dairy_ration(ASSUMED_LITERS), labels[key]
        else:
            label, ration = RATIONS[key][0], RATIONS[key][1]
        table.append({
            'key': key, 'label': label, 'count': row['count'],
            'per_head': {k: str(Decimal(ration[k]).quantize(Decimal('0.1'))) for k in KINDS},
        })
    table.sort(key=lambda r: -r['count'])
    return need, table, warnings


def _actual_daily(item, today):
    """Haqiqiy kunlik sarf (kg) oxirgi 14 kundan, yetarli yozuv bo'lsa."""
    since = today - timedelta(days=USE_LOOKBACK_DAYS - 1)
    agg = InventoryTransaction.objects.filter(
        inventory_item=item, transaction_type='sarf', date__gte=since, date__lte=today
    ).aggregate(used=Sum('quantity'))
    count = InventoryTransaction.objects.filter(
        inventory_item=item, transaction_type='sarf', date__gte=since, date__lte=today).count()
    if not agg['used'] or count < USE_MIN_RECORDS:
        return None
    start = max(since, timezone.localtime(item.created_at).date())
    days = (today - start).days + 1
    if days < USE_MIN_DAYS:
        return None
    unit_kg = item_kg(_unit_one(item))
    return None if unit_kg is None else Decimal(agg['used']) / days * unit_kg


def _unit_one(item):
    clone = InventoryItem(unit=item.unit, kg_per_unit=item.kg_per_unit, quantity=Decimal(1))
    return clone


def build_report(farm, today=None):
    today = today or timezone.localdate()
    need, table, warnings = compute_needs(farm, today)
    items = list(InventoryItem.objects.filter(farm=farm, item_type='ozuqa').order_by('item_name'))

    by_kind = {k: {'stock': Decimal(0), 'items': [], 'actual': None} for k in KINDS}
    unknown_kind, unknown_unit = [], []
    for item in items:
        kind = item_kind(item)
        if kind is None:
            if item.feed_kind != SKIP:
                unknown_kind.append(item)
            continue
        kg = item_kg(item)
        if kg is None:
            unknown_unit.append(item)
            continue
        entry = by_kind[kind]
        entry['stock'] += kg
        actual = _actual_daily(item, today)
        if actual is not None:
            entry['actual'] = (entry['actual'] or Decimal(0)) + actual
        entry['items'].append({'id': item.pk, 'name': item.item_name, 'quantity': str(item.quantity),
                               'unit': item.unit, 'kg': str(kg.quantize(Decimal('0.1')))})

    kinds = []
    for kind in KINDS:
        entry, daily = by_kind[kind], need[kind]
        days_left = None
        if daily > 0 and entry['items']:
            days_left = (entry['stock'] / daily)
        compare = None
        if entry['actual'] is not None and daily > 0:
            ratio = entry['actual'] / daily
            compare = 'kam' if ratio < Decimal('0.6') else 'kop' if ratio > Decimal('1.5') else 'normal'
        kinds.append({
            'kind': kind, 'label': KIND_LABELS[kind],
            'need_kg_per_day': str(daily.quantize(Decimal('0.1'))),
            'stock_kg': str(entry['stock'].quantize(Decimal('1'))),
            'days_left': None if days_left is None else str(days_left.quantize(Decimal('0.1'))),
            'actual_kg_per_day': None if entry['actual'] is None else str(entry['actual'].quantize(Decimal('1'))),
            'compare': compare,
            'has_items': bool(entry['items']),
            'items': entry['items'],
        })

    if unknown_kind:
        warnings.append("Yem turi aniqlanmadi (hisobga olinmadi): " + ", ".join(i.item_name for i in unknown_kind)
                        + ". Mahsulot kartochkasida \"Yem turi\"ni tanlang.")
    if unknown_unit:
        warnings.append("Birligi kg/tonna emas (hisobga olinmadi): " + ", ".join(
            f"{i.item_name} ({i.unit})" for i in unknown_unit) + ". Kartochkada \"Kg/birlik\"ni kiriting.")
    if not table:
        warnings.append("Hisoblash uchun faol hayvon guruhlari yo'q.")

    return {'farm': farm.pk, 'date': today, 'kinds': kinds, 'categories': table, 'warnings': warnings,
            'disclaimer': "Me'yorlar taxminiy (knowledge/yem_ratsion). Aniq ratsionni zootexnik bilan kelishing."}
