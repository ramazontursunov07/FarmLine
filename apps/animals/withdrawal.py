"""
Dori "ushlab turish" muddati: davolashdan keyin sigirning sutini va go'shtini necha kun sotib bo'lmaydi.

Davolash yozuvida (AnimalEvent, turi "davolash") `withdrawal_days` > 0 bo'lsa, shu hayvon uchun
[boshlanish sanasi ... tugash sanasi + withdrawal_days] oralig'idagi sut sotuvga yaroqsiz hisoblanadi.
Davolash hali tugamagan bo'lsa (tugash sanasi yo'q), muddat ochiq: davolash tugamaguncha sotib bo'lmaydi.
Guruhga yozilgan davolashda (aniq hayvon tanlanmagan) guruhdagi barcha faol hayvonlar hisobga olinadi.
"""
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.db.models import Sum

from .models import Animal, AnimalEvent, MilkRecord


def window(event):
    """(boshlanish, tugash) — tugash None bo'lsa muddat ochiq (davolash davom etmoqda)."""
    until = event.end_date + timedelta(days=event.withdrawal_days) if event.end_date else None
    return event.start_date, until


def _events(farm_id):
    return list(AnimalEvent.objects.filter(
        animal_group__farm_id=farm_id, event_type='davolash', withdrawal_days__gt=0,
    ).select_related('medicine', 'animal', 'animal_group'))


def _targets(event, animals_by_group):
    if event.animal_id:
        return [event.animal] if event.animal.status == 'faol' else []
    return animals_by_group.get(event.animal_group_id, [])


def _windows_by_animal(farm_id):
    """{hayvon: [(boshlanish, tugash, dori nomi), ...]}"""
    events = _events(farm_id)
    animals_by_group = defaultdict(list)
    if any(not e.animal_id for e in events):
        for a in Animal.objects.filter(farm_id=farm_id, status='faol'):
            animals_by_group[a.group_id].append(a)
    result = defaultdict(list)
    for e in events:
        start, until = window(e)
        medicine = e.medicine.item_name if e.medicine_id else e.title
        for a in _targets(e, animals_by_group):
            result[a].append((start, until, medicine))
    return result


def active_withdrawals(farm_id, today):
    """
    Bugun sut/go'sht sotib bo'lmaydigan hayvonlar ro'yxati (tugash sanasi bo'yicha tartiblangan).
    Har biri: animal, until (None = davolash davom etmoqda), medicine, days_left.
    """
    rows = []
    for animal, wins in _windows_by_animal(farm_id).items():
        active = [w for w in wins if w[0] <= today and (w[1] is None or w[1] >= today)]
        if not active:
            continue
        ongoing = [w for w in active if w[1] is None]
        if ongoing:
            pick, until = ongoing[0], None
        else:
            pick = max(active, key=lambda w: w[1])
            until = pick[1]
        rows.append({
            'animal': animal, 'until': until, 'medicine': pick[2],
            'days_left': None if until is None else (until - today).days,
        })
    rows.sort(key=lambda r: (r['until'] is None, r['until'] or today, r['animal'].tag_number))
    return rows


def withdrawal_map(farm_id, today):
    """{hayvon id: cheklov qatori} — kartochka va ro'yxatda ko'rsatish uchun."""
    return {r['animal'].pk: r for r in active_withdrawals(farm_id, today)}


def withheld_liters(farm_id, today):
    """Hozir sotuvga yaroqsiz sut (litr): ushlab turish muddatida sog'ilgan sut."""
    wins = _windows_by_animal(farm_id)
    if not wins:
        return Decimal('0')
    first = min(w[0] for items in wins.values() for w in items)
    records = MilkRecord.objects.filter(
        animal_id__in=[a.pk for a in wins], date__gte=first).values_list('animal_id', 'date', 'liters')
    by_id = {a.pk: items for a, items in wins.items()}
    total = Decimal('0')
    for animal_id, day, liters in records:
        for start, until, _ in by_id[animal_id]:
            if start <= day and (until is None or day <= until) and day <= today:
                total += liters
                break
    return total
