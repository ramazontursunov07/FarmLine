"""
Sigirning ko'payish davri eslatmalari: quritish, qayta urug'lantirish va tug'ishlar orasidagi muddat.

Manba: hayvon kartochkasidagi `pregnant_since` / `due_date`, "Tug'ilish" yozuvlari (`AnimalEvent`) va sut yozuvlari.
Faqat qoramol (sigir, buzoq, mol, qoramol turlari) uchun hisoblanadi. Me'yorlar taxminiy:
  * quritish — tug'ishdan ~60 kun oldin (sut bermaydigan "quruq davr" keyingi laktatsiya uchun kerak);
  * qayta urug'lantirish — tug'ishdan keyin ~60 kundan keyin (100 kundan oshsa — kechikdi);
  * tug'ishlar orasi — 365-400 kun yaxshi, 420 kundan oshsa sut yo'qotiladi.
"""
from datetime import timedelta
from decimal import Decimal

from django.db.models import Max

from .models import Animal, AnimalEvent, MilkRecord

DRY_DAYS_BEFORE = 60       # tug'ishdan necha kun oldin quritiladi
DRY_AHEAD_DAYS = 7         # quritishga shuncha kun qolganda eslatma boshlanadi
MILKING_WINDOW_DAYS = 10   # shu kun ichida sut yozuvi bo'lsa, sigir "sog'ilyapti" deb hisoblanadi
REBREED_FROM_DAYS = 60     # tug'ishdan keyin shu kundan qayta urug'lantirish mumkin
REBREED_LATE_DAYS = 100    # shundan keyin urug'lantirilmasa — kechikdi
GESTATION = 283
GOOD_INTERVAL = 400
LONG_INTERVAL = 420

__all__ = ['build_report', 'is_cattle']


def is_cattle(type_name):
    from .serializers import gestation_days
    return gestation_days(type_name) == GESTATION


def _label(a):
    return {'id': a.pk, 'tag_number': a.tag_number, 'name': a.name}


def _verdict(days):
    if days is None:
        return None
    return 'yaxshi' if days <= GOOD_INTERVAL else 'normal' if days <= LONG_INTERVAL else 'uzun'


def build_report(farm, today):
    animals = [
        a for a in Animal.objects.filter(farm=farm, status='faol', sex='urgochi').select_related('group__animal_type')
        if is_cattle(a.group.animal_type.name)
    ]
    ids = [a.pk for a in animals]

    calvings = {}
    for animal_id, d in (AnimalEvent.objects.filter(animal_id__in=ids, event_type='tugilish')
                         .order_by('start_date', 'id').values_list('animal_id', 'start_date')):
        calvings.setdefault(animal_id, []).append(d)
    last_milk = dict(MilkRecord.objects.filter(animal_id__in=ids).values('animal_id')
                     .annotate(m=Max('date')).values_list('animal_id', 'm'))

    dry_off, rebreed, intervals = [], [], []
    interval_values, open_values = [], []

    for a in animals:
        dates = [d for d in calvings.get(a.pk, []) if d <= today]
        last = dates[-1] if dates else None
        row = _label(a)

        # --- Tug'ishlar orasidagi muddat (haqiqiy)
        gaps = [(b - c).days for c, b in zip(dates, dates[1:])]
        interval_values += gaps

        if a.pregnant_since is not None and a.due_date is not None:
            # --- Quritish
            dry_date = a.due_date - timedelta(days=DRY_DAYS_BEFORE)
            milking = a.pk not in last_milk or last_milk[a.pk] >= today - timedelta(days=MILKING_WINDOW_DAYS)
            if milking and a.due_date > today and dry_date <= today + timedelta(days=DRY_AHEAD_DAYS):
                days_to = (dry_date - today).days
                dry_off.append({**row, 'due_date': a.due_date, 'dry_date': dry_date, 'days_to_dry': days_to,
                                'status': 'vaqti' if days_to <= 0 else 'yaqin'})
            # --- Joriy tug'ish oralig'i (rejalashtirilgan)
            if last is not None:
                open_values.append((a.pregnant_since - last).days)
                projected = (a.due_date - last).days
                intervals.append({**row, 'last_calving': last, 'gaps': gaps, 'projected': projected,
                                  'pregnant': True, 'verdict': _verdict(projected)})
        elif last is not None:
            # --- Qayta urug'lantirish (bug'oz emas)
            since = (today - last).days
            projected = since + GESTATION  # bugun urug'lantirilsa, keyingi tug'ish oralig'i shuncha bo'ladi
            status = 'kechikdi' if since >= REBREED_LATE_DAYS else 'vaqti' if since >= REBREED_FROM_DAYS else None
            if status:
                rebreed.append({**row, 'last_calving': last, 'days_since': since, 'status': status,
                                'projected_interval': projected})
            intervals.append({**row, 'last_calving': last, 'gaps': gaps, 'projected': projected,
                              'pregnant': False, 'verdict': _verdict(projected)})

    dry_off.sort(key=lambda r: r['days_to_dry'])
    rebreed.sort(key=lambda r: -r['days_since'])
    intervals.sort(key=lambda r: -(r['projected'] or 0))

    def avg(values):
        return str(Decimal(sum(values) / len(values)).quantize(Decimal('1'))) if values else None

    return {
        'farm': farm.pk, 'date': today,
        'summary': {
            'cows': len(animals), 'avg_interval': avg(interval_values), 'avg_days_open': avg(open_values),
            'dry_off': len(dry_off), 'rebreed': len(rebreed),
            'rebreed_late': sum(1 for r in rebreed if r['status'] == 'kechikdi'),
        },
        'targets': {'dry_days_before': DRY_DAYS_BEFORE, 'rebreed_from': REBREED_FROM_DAYS,
                    'rebreed_late': REBREED_LATE_DAYS, 'good_interval': GOOD_INTERVAL,
                    'long_interval': LONG_INTERVAL},
        'dry_off': dry_off, 'rebreed': rebreed, 'intervals': intervals,
        'disclaimer': "Me'yorlar taxminiy. Quritish va urug'lantirishni veterinar bilan kelishing.",
    }
