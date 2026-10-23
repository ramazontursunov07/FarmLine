"""
Sut tannarxi va har bir sigirning foyda/zarari.

Mavjud ma'lumotdan hisoblanadi: sog'ilgan sut (MilkRecord), sotilgan sut narxi (MilkSale) va
kirim-chiqim (finance.Transaction, "Chiqim").

Muhim cheklov: har bir sigirga qancha yem/dori ketgani alohida yozilmaydi. Shuning uchun umumiy
xarajat sigirlar o'rtasida BIR XIL (har bir sigirga kunlari bo'yicha teng) bo'linadi. Natijada sigirlarning
farqi sog'gan sutiga bog'liq: kam sut beradigan yoki umuman bermaydigan sigir zarar bo'lib chiqadi.
"""
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from django.db.models import Sum

from apps.finance.models import Transaction

from .models import Animal, MilkRecord, MilkSale

ZERO = Decimal('0')
ADULT_DAYS = 365          # shu yoshdan boshlab urg'ochi hayvon "sog'uvchi sigir" hisoblanadi (12 oy)
PRICE_LOOKBACK_DAYS = 90  # tanlangan oyda sotuv bo'lmasa, narx oxirgi shuncha kundagi sotuvdan olinadi
FEW_DAYS = 7              # shundan qisqa davrda natija ishonchsiz bo'lishi mumkin


def month_bounds(month, today):
    """('YYYY-MM' yoki None, bugun) -> (boshi, oxiri). Joriy oyda oxiri = bugun."""
    if month:
        year, mon = (int(x) for x in month.split('-'))
        start = date(year, mon, 1)
    else:
        start = today.replace(day=1)
    next_start = date(start.year + (start.month == 12), start.month % 12 + 1, 1)
    return start, min(next_start - timedelta(days=1), today)


def _money(value):
    return str(Decimal(value).quantize(Decimal('1')))


def _liters(value):
    return str(Decimal(value).quantize(Decimal('0.1')))


def _price(farm, start, end, override):
    """(1 litr narxi yoki None, manba)."""
    if override is not None:
        return override, 'qolda'
    sales = MilkSale.objects.filter(farm=farm, date__gte=start, date__lte=end)
    row = sales.aggregate(l=Sum('liters'), a=Sum('amount'))
    if row['l']:
        return row['a'] / row['l'], 'sotuv'
    row = MilkSale.objects.filter(
        farm=farm, date__gte=end - timedelta(days=PRICE_LOOKBACK_DAYS), date__lte=end
    ).aggregate(l=Sum('liters'), a=Sum('amount'))
    if row['l']:
        return row['a'] / row['l'], 'sotuv_90'
    return None, None


def parse_price(raw):
    if raw in (None, ''):
        return None
    try:
        value = Decimal(str(raw))
    except InvalidOperation:
        return None
    return value if value > 0 else None


def build_report(farm, start, end, exclude=(), price_override=None):
    days = (end - start).days + 1

    # --- xarajatlar (haqiqiy to'langan pul, "Chiqim")
    categories = dict(Transaction.CATEGORY_CHOICES)
    spent = {
        r['category']: r['t']
        for r in Transaction.objects.filter(
            farm=farm, transaction_type='chiqim', date__gte=start, date__lte=end
        ).values('category').annotate(t=Sum('amount')).order_by()
    }
    cost_rows = [
        {'category': k, 'label': categories.get(k, k), 'amount': _money(v), 'included': k not in exclude}
        for k, v in sorted(spent.items(), key=lambda kv: -kv[1])
    ]
    cost = sum((v for k, v in spent.items() if k not in exclude), ZERO)

    # --- sut
    liters_by_animal = {
        r['animal_id']: r for r in MilkRecord.objects.filter(
            animal__farm=farm, date__gte=start, date__lte=end
        ).values('animal_id').annotate(l=Sum('liters')).order_by()
    }
    total_liters = sum((r['l'] for r in liters_by_animal.values()), ZERO)
    price, price_source = _price(farm, start, end, price_override)

    # --- sigirlar va ularning kunlari
    cows = []
    for a in Animal.objects.filter(farm=farm, sex='urgochi').select_related('group'):
        has_milk = a.pk in liters_by_animal
        if a.status != 'faol' and not has_milk:
            continue
        adult_from = a.birth_date + timedelta(days=ADULT_DAYS) if a.birth_date else start
        if a.status == 'faol' and adult_from > end and not has_milk:
            continue  # hali sigir emas (buzoq/g'unajin)
        first = max(start, adult_from) if not has_milk else start
        cow_days = max((end - first).days + 1, 1)
        cows.append((a, cow_days))
    total_cow_days = sum(d for _, d in cows)

    rows = []
    for a, cow_days in cows:
        liters = liters_by_animal.get(a.pk, {}).get('l', ZERO)
        share = cost * cow_days / total_cow_days if total_cow_days else ZERO
        revenue = liters * price if price is not None else None
        profit = revenue - share if revenue is not None else None
        if liters == 0:
            verdict = 'sut_yoq'
        elif profit is None:
            verdict = 'narx_yoq'
        else:
            verdict = 'zarar' if profit < 0 else 'foyda'
        rows.append({
            'id': a.pk, 'tag_number': a.tag_number, 'name': a.name, 'active': a.status == 'faol',
            'status': a.get_status_display(),
            'days': cow_days,
            'liters': _liters(liters),
            'daily_avg': _liters(liters / cow_days) if cow_days else '0.0',
            'cost': _money(share),
            'revenue': _money(revenue) if revenue is not None else None,
            'profit': _money(profit) if profit is not None else None,
            'cost_per_liter': _money(share / liters) if liters else None,
            # kuniga kamida shuncha litr sog'masa, sigir o'z xarajatini qoplamaydi
            'break_even_daily': _liters(share / cow_days / price) if price and cow_days else None,
            'verdict': verdict,
        })
    # Eng zararlisi tepada; narx noma'lum bo'lsa, eng kam sut bergani tepada
    rows.sort(key=lambda r: (Decimal(r['profit']) if r['profit'] is not None else Decimal(r['liters'])))

    revenue_total = total_liters * price if price is not None else None
    warnings = []
    if total_liters == 0:
        warnings.append("Bu davrda sog'ilgan sut yozilmagan: tannarxni hisoblab bo'lmaydi.")
    if price is None:
        warnings.append("Sut narxi noma'lum (sotuv yo'q). 1 litr narxini o'zingiz kiriting.")
    if cost == 0:
        warnings.append("Bu davrda chiqim yozilmagan: tannarx 0 chiqdi.")
    if days < FEW_DAYS:
        warnings.append(f"Davr juda qisqa ({days} kun): natija aniq bo'lmasligi mumkin.")

    return {
        'farm': farm.pk,
        'month': f"{start:%Y-%m}",
        'start': start, 'end': end, 'days': days,
        'totals': {
            'liters': _liters(total_liters),
            'cost': _money(cost),
            'cost_per_liter': _money(cost / total_liters) if total_liters else None,
            'price_per_liter': _money(price) if price is not None else None,
            'price_source': price_source,
            'revenue': _money(revenue_total) if revenue_total is not None else None,
            'profit': _money(revenue_total - cost) if revenue_total is not None else None,
            'cows': len(rows),
            'losing_cows': sum(1 for r in rows if r['verdict'] in ('zarar', 'sut_yoq')),
        },
        'costs': cost_rows,
        'cows': rows,
        'warnings': warnings,
    }
