"""
Sut sigirlarining ko'payish tsikli: quritish, qayta urug'lantirish va tug'ishlar orasidagi muddat.

Chorvadorlar sutni asosan shu uch joyda yo'qotadi:
  * Quritish -- tug'ishdan ~60 kun oldin sog'ishni to'xtatish. Kech quritilsa, sigir dam olmaydi va keyingi
    laktatsiyada sut kamayadi.
  * Qayta urug'lantirish -- tug'gandan ~60 kundan keyin boshlanadi. Har bir bo'sh kun (bug'oz bo'lmagan kun)
    laktatsiyani cho'zadi, lekin sut kamayib boradi: sigir "sutsiz va bug'ozsiz" yuradi.
  * Tug'ishlar orasi -- maqsad ~12-13 oy (400 kundan oshmasin). Bug'ozlik 283 kun, shuning uchun sigir tug'gandan
    keyin ko'pi bilan ~117 kun ichida bug'oz bo'lishi kerak.

Hamma raqam shu faylning tepasidagi sozlamalardan. Hisoblash faqat qoramollar (sigir/mol) uchun: qo'y, echki va
boshqalarning muddatlari boshqacha, ularga noto'g'ri eslatma bermaymiz.
API (hayvon kartochkasi) ham, Telegram eslatma ham aynan shu yerdan oladi, shuning uchun raqamlar farq qilmaydi.
"""
from datetime import timedelta

from django.db.models import Max

from .models import Animal, AnimalEvent, MilkRecord

# --- Quritish ---
DRY_OFF_DAYS_BEFORE_CALVING = 60  # tug'ishdan necha kun oldin quritiladi
DRY_OFF_REMIND_AHEAD = 7  # quritish sanasiga shuncha kun qolganda eslatma boshlanadi
MILK_STOPPED_DAYS = 7  # shuncha kun sut yozilmasa, sigir allaqachon quritilgan deb hisoblanadi

# --- Qayta urug'lantirish va tug'ishlar orasi ---
REBREED_FROM_DAYS = 60  # tug'gandan keyin urug'lantirish shu kundan boshlanadi
REBREED_LATE_DAYS = 90  # shu kundan keyin "kechikmoqda"
CALVING_INTERVAL_TARGET = 400  # tug'ishlar orasi maqsadi (kun)
GESTATION_DAYS = 283  # qoramol bug'ozligi
CONCEIVE_BY_DAYS = CALVING_INTERVAL_TARGET - GESTATION_DAYS  # 117: shundan keyin interval maqsaddan oshadi
REBREED_MAX_DAYS = 300  # tug'gandan shuncha kundan keyin eslatilmaydi (ehtimol ma'lumot eskirgan)
MIN_REAL_INTERVAL = 200  # ikki tug'ish orasi bundan kam bo'lsa, ikkinchisi xato yozuv deb olinadi


def is_cattle(animal):
    """Qoramolmi (sigir, mol, buzoq...)? Tur nomidan aniqlanadi (bug'ozlik muddati 283 kun bo'lgan turlar)."""
    from .serializers import gestation_days  # circular import bo'lmasligi uchun shu yerda
    return gestation_days(animal.group.animal_type.name) == GESTATION_DAYS


def calving_dates(animal_ids):
    """
    Har bir hayvonning tug'gan sanalari: {animal_id: [eng yangisi, undan oldingisi, ...]}.
    Manba: «Tug'ilish» voqealari va hayvon onasi sifatida ko'rsatilgan buzoqlarning tug'ilgan sanasi
    (kartochkani qo'lda ochgan bo'lsa ham). Egizaklar bitta sana bo'lib qoladi.
    """
    ids = list(animal_ids)
    found = {pk: set() for pk in ids}
    for pk, d in AnimalEvent.objects.filter(animal_id__in=ids, event_type='tugilish').values_list(
            'animal_id', 'start_date'):
        found[pk].add(d)
    for pk, d in Animal.objects.filter(mother_id__in=ids, birth_date__isnull=False).values_list(
            'mother_id', 'birth_date'):
        found[pk].add(d)

    result = {}
    for pk, dates in found.items():
        kept = []
        for d in sorted(dates, reverse=True):
            # Ikki tug'ish orasi 200 kundan kam bo'lishi mumkin emas: taxminiy kiritilgan sana bo'lsa, tashlab ketamiz
            if not kept or (kept[-1] - d).days >= MIN_REAL_INTERVAL:
                kept.append(d)
        result[pk] = kept
    return result


def last_milk_dates(animal_ids):
    """{animal_id: oxirgi sut yozilgan sana}. Sut umuman yozilmagan hayvon ro'yxatda bo'lmaydi."""
    rows = (
        MilkRecord.objects.filter(animal_id__in=list(animal_ids))
        .order_by().values('animal_id').annotate(last=Max('date')).values_list('animal_id', 'last')
    )
    return dict(rows)


def collect(animal_ids):
    """Bir nechta hayvon uchun kerakli ma'lumotlarni bir marta (2 ta so'rov bilan) yig'adi."""
    ids = list(animal_ids)
    return {'calvings': calving_dates(ids), 'milk': last_milk_dates(ids)}


def info(animal, today, calvings=None, last_milk=None):
    """
    Bitta hayvonning tsikli. Qoramol bo'lmasa, urg'ochi bo'lmasa yoki faol bo'lmasa, None.

    dry_off_state:   None | 'soon' (quritishga <=7 kun) | 'now' (bugun) | 'late' (kechikdi) | 'done' (quritilgan)
    rebreed_state:   None (bug'oz yoki tug'magan) | 'waiting' (<60 kun) | 'now' (60-89) | 'late' (90-116)
                     | 'critical' (>=117: tug'ishlar orasi maqsaddan oshadi)
    """
    if animal.sex != 'urgochi' or animal.status != 'faol' or not is_cattle(animal):
        return None
    calvings = calvings if calvings is not None else calving_dates([animal.pk]).get(animal.pk, [])
    pregnant = animal.pregnant_since is not None

    out = {
        'dried_off_on': animal.dried_off_on, 'dry_off_date': None, 'days_to_dry_off': None, 'dry_off_state': None,
        'days_since_calving': None, 'rebreed_state': None, 'rebreed_from': None, 'conceive_by': None,
        'calving_interval_days': None, 'expected_interval_days': None, 'interval_long': False,
    }

    last_calving = calvings[0] if calvings else None
    if last_calving:
        out['days_since_calving'] = (today - last_calving).days
        out['rebreed_from'] = last_calving + timedelta(days=REBREED_FROM_DAYS)
        out['conceive_by'] = last_calving + timedelta(days=CONCEIVE_BY_DAYS)
        if len(calvings) > 1:
            out['calving_interval_days'] = (calvings[0] - calvings[1]).days

    if pregnant:
        if animal.due_date is not None:
            dry = animal.due_date - timedelta(days=DRY_OFF_DAYS_BEFORE_CALVING)
            out['dry_off_date'] = dry
            out['days_to_dry_off'] = (dry - today).days
            if last_milk is None:
                last_milk = last_milk_dates([animal.pk]).get(animal.pk)
            already_dry = animal.dried_off_on is not None or (
                    last_milk is not None and (today - last_milk).days >= MILK_STOPPED_DAYS)
            if animal.due_date < today:
                pass  # tug'ish muddati o'tdi: endi tug'ish eslatmasi muhim, quritish emas
            elif already_dry:
                out['dry_off_state'] = 'done'
            elif dry < today:
                out['dry_off_state'] = 'late'
            elif dry == today:
                out['dry_off_state'] = 'now'
            elif (dry - today).days <= DRY_OFF_REMIND_AHEAD:
                out['dry_off_state'] = 'soon'
        if last_calving:
            # Hozirgi bug'ozlik bilan tug'ishlar orasi qancha bo'lishi: urug'lantirish kech bo'lsa, uzayib ketadi
            out['expected_interval_days'] = (animal.due_date - last_calving).days if animal.due_date else (
                    (animal.pregnant_since - last_calving).days + GESTATION_DAYS)
    elif last_calving:
        days = out['days_since_calving']
        if days >= CONCEIVE_BY_DAYS:
            out['rebreed_state'] = 'critical'
        elif days >= REBREED_LATE_DAYS:
            out['rebreed_state'] = 'late'
        elif days >= REBREED_FROM_DAYS:
            out['rebreed_state'] = 'now'
        else:
            out['rebreed_state'] = 'waiting'

    interval = out['calving_interval_days']
    expected = out['expected_interval_days']
    out['interval_long'] = bool(
        (interval and interval > CALVING_INTERVAL_TARGET) or (expected and expected > CALVING_INTERVAL_TARGET))
    return out
