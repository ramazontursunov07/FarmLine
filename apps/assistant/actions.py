"""AI harakatlari: fermer gapirib/yozib aytadi, AI taklif qiladi, foydalanuvchi tasdiqlaydi, tizim bajaradi.

Xavfsizlik qoidalari (shu fayldagi hamma narsa shularga tayanadi):
  1. AI hech narsani o'zi bajarmaydi. U faqat taklif yozadi; bajarishni foydalanuvchi "Tasdiqlash" bilan boshlaydi.
  2. AI taklifidagi hech narsaga ishonilmaydi: mahsulot, ferma, miqdor, summa serverda qayta topiladi va
     tekshiriladi. Foydalanuvchiga ko'rsatiladigan tasdiq kartasi AI matnidan emas, SERVER topgan
     ma'lumotdan tuziladi (AI "5 kg" desa-yu, server 50 kg topsa ham, karta haqiqatni ko'rsatadi).
  3. Bajarish oddiy API'dagi o'sha view'larning perform_create() metodi orqali ketadi: ruxsatlar, zaxira
     tekshiruvi va Telegram ogohlantirishlari ikki joyda takrorlanmaydi va farq qilib qolmaydi.
  4. Bir nechta amal bitta tranzaksiyada: biri xato bo'lsa, hech biri yozilmaydi.
"""
import json
import re
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework.exceptions import ValidationError

from apps.animals.models import Animal
from apps.animals.serializers import MilkRecordSerializer
from apps.animals.views import MilkRecordViewSet
from apps.finance.models import Transaction
from apps.finance.serializers import TransactionSerializer
from apps.finance.views import TransactionViewSet, finance_farms
from apps.inventory.models import InventoryItem
from apps.inventory.serializers import InventoryTransactionSerializer
from apps.inventory.views import InventoryTransactionViewSet, fmt
from apps.users.digest import money
from apps.users.permissions import is_app_admin

from .models import PendingAction

MARKER = '[[ACTION]]'
MAX_ACTIONS = 3        # bitta xabardan ko'pi bilan nechta amal
MAX_PROMPT_ITEMS = 40  # AI ga ko'rsatiladigan ombor mahsulotlari soni
MAX_PROMPT_COWS = 60   # AI ga ko'rsatiladigan sigirlar soni
MAX_MILK_ENTRIES = 50  # bitta sut harakatida ko'pi bilan nechta sigir
MILK_SESSIONS = {'ertalab': 'Ertalab', 'kechqurun': 'Kechqurun', 'kun': 'Butun kun'}
KEEP_HISTORY_DAYS = 7  # tugagan yozuvlar shuncha kun saqlanadi

INVENTORY_TYPES = {'inventory_use': 'sarf', 'inventory_add': 'kirim'}
ALL_TYPES = set(INVENTORY_TYPES) | {'finance', 'milk'}
FINANCE_KINDS = ('kirim', 'chiqim')


class Question(str):
    """Xato emas: yetishmayotgan ma'lumotni (masalan, narxni) so'raydigan xabar. Suhbatda oddiy savol bo'lib chiqadi."""


# ---------------------------------------------------------------- AI ga ko'rsatma

def _accessible_items(user):
    return (
        InventoryItem.objects.select_related('farm')
        .filter(Q(farm__owner=user) | Q(farm__workers__user=user))
        .distinct().order_by('farm__name', 'item_name')
    )


def _accessible_cows(user):
    """Foydalanuvchi sut yoza oladigan faol urg'ochi hayvonlar."""
    return (
        Animal.objects.select_related('farm')
        .filter(Q(farm__owner=user) | Q(farm__workers__user=user), status='faol', sex='urgochi')
        .distinct().order_by('farm__name', 'tag_number')
    )


def build_action_prompt(user, today=None):
    """AI ga harakat yozish qoidalarini va unga kerak ro'yxatlarni beradi. Harakat qila olmaydigan bo'lsa, ''."""
    if is_app_admin(user):
        return ''
    today = today or timezone.localdate()
    items = list(_accessible_items(user)[:MAX_PROMPT_ITEMS])
    farms = list(finance_farms(user).order_by('name'))
    cows = list(_accessible_cows(user)[:MAX_PROMPT_COWS])
    if not items and not farms and not cows:
        return ''

    lines = [
        "HARAKATLAR. Foydalanuvchi ombor, kirim-chiqim yoki sut miqdoriga biror narsa YOZISHNI so'rasa "
        "(masalan «ombordan 50 kg yem chiqar», «bugun 200 000 so'm yem uchun chiqim yoz», «14-sigir 12 litr sut berdi»), "
        "javobingni 1 jumlada yoz va eng oxirida, alohida qatorda shu formatda harakat qo'sh:",
        f"{MARKER} [{{...}}, {{...}}]",
        "Qatorda faqat JSON ro'yxat bo'lsin (kod bloki, izoh, qo'shimcha matn yo'q).",
        "Sen hech narsani o'zing bajarmaysan: foydalanuvchi tasdiqlagach tizim yozadi. "
        "Shuning uchun «bajardim», «yozdim» dema; faqat tushunganingni ayt. Natijani tizim ko'rsatadi, "
        "raqamlarni matnda takrorlama.",
        "Faqat foydalanuvchi aniq yozishni so'raganda harakat qo'sh. Savol, maslahat yoki hisobot "
        "so'ralsa, harakat qo'shma. Foydalanuvchi shunchaki «ha» yoki «tasdiqlayman» desa, harakat "
        "qo'shma: tasdiqlash tugmasini bosishini ayt.",
        "Mahsulot yoki miqdor yoki summa aniq bo'lmasa, o'ylab topma: harakat qo'shmasdan, bitta "
        "qisqa aniqlashtiruvchi savol ber. Ko'p bo'lsa ham eng ko'pi bilan "
        f"{MAX_ACTIONS} ta harakat yoz. Raqamni oddiy son qilib yoz (200 000 so'm -> 200000).",
        "Harakat turlari:",
    ]
    if items:
        lines += [
            '  {"type": "inventory_use", "item": "<mahsulot nomi>", "quantity": <son>, "note": "<ixtiyoriy izoh>"}'
            "  -- ombordan chiqarish/sarflash",
            '  {"type": "inventory_add", "item": "<mahsulot nomi>", "quantity": <son>, '
            + ('"amount": <jami narxi, so\'m>, ' if farms else '')
            + '"note": "<ixtiyoriy izoh>"}  -- omborga kirim (yangi keltirilgan)',
            "  «item» ni quyidagi ro'yxatdan AYNAN ko'chirib yoz. Ro'yxatda yo'q mahsulot uchun harakat yozma.",
            "  «ishlatdim», «sarfladim», «berdim» (yem, dori) -> inventory_use; «keldi», «oldim», «sotib oldim» -> "
            "inventory_add. Foydalanuvchi boshqa birlikda aytsa (masalan «5 qop») va mahsulot birligi boshqa bo'lsa "
            "(masalan kg), 1 qop necha kg ekani noma'lum bo'lsa o'ylab topma: «1 qop necha kg?» deb so'ra.",
        ]
        if farms:
            lines.append(
                "  Omborga kirim (inventory_add) uchun «amount» (JAMI narx, so'mda) kerak. Foydalanuvchi narxni "
                "aytmagan bo'lsa, harakat qo'shmasdan «Necha so'mga oldingiz?» deb so'ra. Narx kg/tonna/dona "
                "uchun aytilsa, miqdorga ko'paytirib JAMI summani yoz. Foydalanuvchi narxi yo'q desa "
                "(bepul, sovg'a, bilmayman), amount: 0 yoz. Narx tizimda avtomatik «Chiqim» bo'lib yoziladi, "
                "shuning uchun xuddi shu xarid uchun alohida «finance» chiqim YOZMA (balans ikki marta kamayib ketadi)."
            )
    if farms:
        cats = ", ".join(f"{k} ({v})" for k, v in Transaction.CATEGORY_CHOICES)
        lines += [
            '  {"type": "finance", "kind": "chiqim" yoki "kirim", "category": "<kategoriya>", '
            '"amount": <so\'m>, "description": "<qisqa izoh>", "date": "YYYY-MM-DD"}  -- kirim-chiqim yozish',
            f"  kategoriya: {cats}. «date» ni foydalanuvchi sana aytmasa, tushirib qoldir (bugun bo'ladi).",
        ]
    if cows:
        lines += [
            '  {"type": "milk", "entries": [{"animal": "<quloq raqami>", "liters": <son>}, ...], '
            '"session": "ertalab" yoki "kechqurun" yoki "kun", "date": "YYYY-MM-DD"}'
            "  -- sigirlardan sog'ilgan sutni yozish",
            "  Sut HAR BIR SIGIR bo'yicha alohida yoziladi: «animal» ni quyidagi ro'yxatdan quloq raqami bilan yoz. "
            "Foydalanuvchi faqat umumiy litrni aytsa (masalan «bugun 85 litr sut») va qaysi sigirlardan ekanini "
            "aytmasa, o'ylab topma va sigirlarga bo'lib yuborma: harakat qo'shmasdan «Qaysi sigirdan necha litr? "
            "Masalan: 14-sigir 12 litr, 15-sigir 9 litr» deb so'ra.",
            "  «session»: ertalab yoki kechqurun aytilsa shuni yoz, aytilmasa «kun» (butun kun). «date» ni "
            "foydalanuvchi sana aytmasa, tushirib qoldir (bugun bo'ladi).",
        ]
    if len(farms) > 1 or len({i.farm_id for i in items}) > 1:
        lines.append('  Bir nechta ferma bo\'lsa, ferma aytilganda "farm": "<ferma nomi>" ni ham qo\'sh.')

    lines.append(f"Bugungi sana: {today:%Y-%m-%d}.")
    if items:
        lines.append("Ombordagi mahsulotlar (nomi — hozirgi miqdor — ferma):")
        for it in items:
            lines.append(f"  • {it.item_name} — {fmt(it.quantity)} {it.unit} — {it.farm.name}")
    if cows:
        lines.append("Sut yozish mumkin bo'lgan sigirlar (quloq raqami — laqabi — ferma):")
        for c in cows:
            lines.append(f"  • №{c.tag_number}" + (f" — {c.name}" if c.name else "") + f" — {c.farm.name}")
    if farms:
        lines.append("Kirim-chiqim yozish mumkin bo'lgan fermalar: " + ", ".join(f.name for f in farms))
    else:
        lines.append("Bu foydalanuvchi kirim-chiqim yoza olmaydi (huquqi yo'q): «finance» harakatini yozma.")
    return "\n".join(lines)


# ---------------------------------------------------------------- AI javobini o'qish

def extract_action(answer):
    """AI javobidan harakat qismini ajratadi. (ko'rinadigan matn, xom amallar ro'yxati yoki None) qaytaradi.

    Belgi (MARKER) va JSON hech qachon foydalanuvchiga ko'rsatilmaydi: JSON buzuq bo'lsa ham,
    faqat matn qismi qoladi (u holda harakat taklif qilinmaydi).
    """
    if MARKER not in answer:
        return answer, None
    text, _, rest = answer.partition(MARKER)
    rest = rest.strip().lstrip('`').strip()
    if rest[:4].lower() == 'json':
        rest = rest[4:].strip()
    raw = None
    try:
        parsed, _end = json.JSONDecoder().raw_decode(rest)
        if isinstance(parsed, dict):
            parsed = [parsed]
        if isinstance(parsed, list):
            raw = parsed
    except ValueError:
        pass
    return text.strip(), raw


# ---------------------------------------------------------------- qidirish va tekshirish

_APOSTROPHES = str.maketrans({c: "'" for c in "ʻʼ‘’`´"})


def _tokens(value):
    """«O'rta Yem!» -> ['orta', 'yem']: apostrof turlari va tinish belgilari farq qilmasin."""
    text = str(value or '').lower().translate(_APOSTROPHES).replace("'", '')
    return re.sub(r'[^\w\s]', ' ', text).split()


def _decimal(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        if isinstance(value, (int, float)):
            number = Decimal(str(value))
        else:
            s = re.sub(r'[\s_\u00a0]', '', str(value))
            s = s.replace(',', '.') if s.count(',') == 1 and '.' not in s else s.replace(',', '')
            number = Decimal(s)
    except (InvalidOperation, ValueError):
        return None
    return number if number.is_finite() else None


def _names(objs, attr, limit=8):
    return ", ".join(f"«{getattr(o, attr)}»" for o in objs[:limit])


def _find_item(user, name, farm_name):
    """Foydalanuvchi omboridan mahsulotni topadi. (item, None) yoki (None, foydalanuvchiga xabar)."""
    items = list(_accessible_items(user))
    query = _tokens(name)
    if not query:
        return None, "Qaysi mahsulot ekani aytilmadi."

    if farm_name:
        ftokens = _tokens(farm_name)
        in_farm = [i for i in items if all(t in _tokens(i.farm.name) or t in i.farm.name.lower() for t in ftokens)]
        if in_farm:
            items = in_farm

    exact = [i for i in items if _tokens(i.item_name) == query]
    found = exact or [
        i for i in items
        if all(any(t in word for word in _tokens(i.item_name)) for t in query)
    ]
    if not found:
        have = f" Omborda: {_names(items, 'item_name')}." if items else ""
        return None, f"Omborda «{name}» topilmadi.{have}"
    if len(found) > 1:
        listing = ", ".join(f"«{i.item_name}» ({i.farm.name})" for i in found[:6])
        return None, f"«{name}» deganda bir nechta mahsulot bor: {listing}. Qaysi biri?"
    return found[0], None


def _find_finance_farm(user, farm_name):
    farms = list(finance_farms(user).order_by('name'))
    if not farms:
        return None, "Sizda kirim-chiqim yozish huquqi yo'q."
    if farm_name:
        ftokens = _tokens(farm_name)
        match = [f for f in farms if all(t in _tokens(f.name) or t in f.name.lower() for t in ftokens)]
        if len(match) == 1:
            return match[0], None
        if not match:
            return None, f"«{farm_name}» nomli ferma topilmadi. Fermalaringiz: {_names(farms, 'name')}."
        farms = match
    if len(farms) == 1:
        return farms[0], None
    return None, f"Qaysi fermaga yozay? {_names(farms, 'name')}"


def _validated_date(raw, today):
    """(sana, xato). Sana aytilmasa yoki o'qib bo'lmasa, bugun."""
    if raw in (None, ''):
        return today, None
    try:
        value = parse_date(str(raw))
    except ValueError:
        value = None
    if value is None:
        return today, None
    if value > today:
        return None, "Kelajak sanasi bilan yozib bo'lmaydi."
    return value, None


def _resolve_inventory(user, raw, today):
    kind = INVENTORY_TYPES[raw['type']]
    item, problem = _find_item(user, raw.get('item'), raw.get('farm'))
    if problem:
        return None, problem
    quantity = _decimal(raw.get('quantity'))
    if quantity is None or quantity <= 0:
        return None, f"«{item.item_name}» uchun miqdor aniq emas."
    if kind == 'sarf' and quantity > item.quantity:
        return None, (f"Omborda «{item.item_name}» yetarli emas: hozir {fmt(item.quantity)} {item.unit}, "
                      f"siz {fmt(quantity)} {item.unit} so'radingiz.")

    # Kirim narxi: u moliyada avtomatik "Chiqim" bo'ladi (balansdan ayriladi)
    amount, can_pay = None, False
    if kind == 'kirim':
        can_pay = finance_farms(user).filter(pk=item.farm_id).exists()
        raw_amount = raw.get('amount')
        if can_pay:
            if raw_amount in (None, ''):
                return None, Question(
                    f"«{item.item_name}» kirimi necha so'mga olindi? Jami narxni ayting "
                    f"(narxi yo'q bo'lsa, «narxsiz» deng)."
                )
            amount = _decimal(raw_amount)
            if amount is None or amount < 0:
                return None, f"«{item.item_name}»: narx aniq emas."
        elif (_decimal(raw_amount) or 0) > 0:
            return None, (f"«{item.item_name}»: narxni yozish uchun moliya huquqi kerak. "
                          f"Narxsiz kirim qiling, ferma egasi moliyaga qo'shadi.")

    note = str(raw.get('note') or '').strip()[:200]
    data = {
        'inventory_item': item.pk,
        'transaction_type': kind,
        'quantity': str(quantity),
        'date': today.isoformat(),
        'note': (note + ' ' if note else '') + '(AI orqali)',
    }
    if amount:
        data['amount'] = str(amount)
    serializer = InventoryTransactionSerializer(data=data)
    if not serializer.is_valid():
        if 'amount' in serializer.errors:
            return None, f"«{item.item_name}»: narx noto'g'ri (ko'pi bilan 2 ta kasr raqami, 12 ta raqam)."
        return None, f"«{item.item_name}»: miqdor noto'g'ri (ko'pi bilan 2 ta kasr raqami)."

    after = item.quantity - quantity if kind == 'sarf' else item.quantity + quantity
    details = [
        f"Mahsulot: {item.item_name}",
        f"Miqdor: {fmt(quantity)} {item.unit}",
        f"Omborda: {fmt(item.quantity)} → {fmt(after)} {item.unit}",
        f"Ferma: {item.farm.name}",
    ]
    if amount:
        details.append(f"Narxi: {money(amount)} so'm (moliyada «Chiqim» bo'lib yoziladi, balansdan ayriladi)")
    elif kind == 'kirim' and can_pay:
        details.append("Narxi: kiritilmadi (moliyaga yozilmaydi)")
    if note:
        details.append(f"Izoh: {note}")
    return {
        'type': raw['type'],
        'data': data,
        'title': "📦 Ombordan chiqarish" if kind == 'sarf' else "📥 Omborga kirim",
        'details': details,
    }, None


def _resolve_finance(user, raw, today):
    farm, problem = _find_finance_farm(user, raw.get('farm'))
    if problem:
        return None, problem
    kind = str(raw.get('kind') or '').lower()
    if kind not in FINANCE_KINDS:
        return None, "Kirimmi yoki chiqimmi, aniq emas."
    amount = _decimal(raw.get('amount'))
    if amount is None or amount <= 0:
        return None, "Summa aniq emas."
    date, problem = _validated_date(raw.get('date'), today)
    if problem:
        return None, problem

    categories = dict(Transaction.CATEGORY_CHOICES)
    wanted = str(raw.get('category') or '').strip().lower()
    category = next((k for k, v in categories.items() if wanted in (k, v.lower())), 'boshqa')
    description = str(raw.get('description') or '').strip()[:200]

    data = {
        'farm': farm.pk,
        'transaction_type': kind,
        'category': category,
        'amount': str(amount),
        'description': (description + ' ' if description else '') + '(AI orqali)',
        'date': date.isoformat(),
    }
    if not TransactionSerializer(data=data).is_valid():
        return None, "Summa noto'g'ri (ko'pi bilan 2 ta kasr raqami, 12 ta raqam)."

    details = [
        f"Summa: {money(amount)} so'm",
        f"Kategoriya: {categories[category]}",
        f"Sana: {date:%d.%m.%Y}",
        f"Ferma: {farm.name}",
    ]
    if description:
        details.append(f"Izoh: {description}")
    if kind == 'chiqim' and Transaction.objects.filter(
        farm=farm, transaction_type='chiqim', amount=amount, inventory_purchase__isnull=False,
        created_at__gte=timezone.now() - timedelta(hours=24),
    ).exists():
        details.append(
            "⚠️ Diqqat: xuddi shu summa so'nggi 24 soatda ombor kirimi bilan allaqachon chiqim bo'lib yozilgan. "
            "Bu takror bo'lsa, tasdiqlamang."
        )
    return {
        'type': 'finance',
        'data': data,
        'title': "💸 Chiqim yozish" if kind == 'chiqim' else "💰 Kirim yozish",
        'details': details,
    }, None


def _norm_tag(value):
    """«№14», «14-sigir», «UZ-123» kabi yozuvlar quloq raqami bilan solishtirish uchun tozalanadi."""
    return re.sub(r'[^0-9a-z]', '', str(value or '').lower().translate(_APOSTROPHES))


def _find_cow(user, ref, farm_name):
    """Sigirni quloq raqami (yoki laqabi) bo'yicha topadi. (hayvon, None) yoki (None, foydalanuvchiga xabar)."""
    cows = list(_accessible_cows(user))
    if farm_name:
        ftokens = _tokens(farm_name)
        in_farm = [c for c in cows if all(t in _tokens(c.farm.name) or t in c.farm.name.lower() for t in ftokens)]
        cows = in_farm or cows
    tokens = [t for t in _tokens(ref) if t not in ('sigir', 'no', 'nomer', 'raqam', 'raqamli', 'quloq')]
    if not tokens:
        return None, "Qaysi sigir ekani aytilmadi."

    by_tag = [c for c in cows if _norm_tag(c.tag_number) and _norm_tag(c.tag_number) in {_norm_tag(t) for t in tokens}]
    if not by_tag:
        by_tag = [c for c in cows if _norm_tag(c.tag_number) == _norm_tag(ref)]
    found = by_tag or [c for c in cows if c.name and all(t in _tokens(c.name) for t in tokens)]
    if not found:
        return None, f"«{ref}» raqamli faol sigir topilmadi."
    if len(found) > 1:
        listing = ", ".join(f"№{c.tag_number} ({c.farm.name})" for c in found[:6])
        return None, f"«{ref}» deganda bir nechta sigir bor: {listing}. Qaysi fermadan?"
    return found[0], None


def _first_error(errors):
    """DRF xatolar lug'atidan birinchi xabarni oladi."""
    for value in errors.values():
        first = value[0] if isinstance(value, (list, tuple)) and value else value
        return str(first)
    return "noto'g'ri ma'lumot"


def _resolve_milk(user, raw, today, problems):
    """Sut yozish: bir nechta sigir. Yaroqli yozuvlardan karta tuziladi, yaroqsizlari `problems` ga qo'shiladi."""
    entries = raw.get('entries')
    if not isinstance(entries, list):
        entries = [{'animal': raw.get('animal'), 'liters': raw.get('liters')}] if raw.get('animal') else []
    if not entries:
        problems.append(Question("Qaysi sigirdan necha litr sut yozay? Masalan: 14-sigir 12 litr, 15-sigir 9 litr."))
        return None

    session = str(raw.get('session') or 'kun').lower()
    if session not in MILK_SESSIONS:
        session = 'kun'
    date, problem = _validated_date(raw.get('date'), today)
    if problem:
        problems.append(problem)
        return None

    records, rows, seen = [], [], set()
    for entry in entries[:MAX_MILK_ENTRIES]:
        if not isinstance(entry, dict):
            continue
        cow, problem = _find_cow(user, entry.get('animal'), entry.get('farm') or raw.get('farm'))
        if problem:
            problems.append(problem)
            continue
        label = f"№{cow.tag_number}"
        liters = _decimal(entry.get('liters'))
        if liters is None or liters <= 0:
            problems.append(f"{label}: litr aniq emas.")
            continue
        if liters > 100:
            problems.append(f"{label}: bir sigirdan 100 litrdan ko'p bo'lmaydi, raqamni tekshiring.")
            continue
        if liters != liters.quantize(Decimal('0.1')):
            problems.append(f"{label}: litr ko'pi bilan 1 ta kasr raqami bilan yoziladi (masalan 12.5).")
            continue
        if cow.pk in seen:
            problems.append(f"{label}: bir xabarda ikki marta yozilgan.")
            continue
        data = {'animal': cow.pk, 'date': date.isoformat(), 'session': session, 'liters': str(liters)}
        serializer = MilkRecordSerializer(data=data)
        if not serializer.is_valid():
            problems.append(f"{label}: {_first_error(serializer.errors)}")
            continue
        seen.add(cow.pk)
        records.append(data)
        rows.append((cow, liters))

    if not records:
        return None
    total = sum((liters for _cow, liters in rows), Decimal('0'))
    details = [f"Sana: {date:%d.%m.%Y}", f"Vaqt: {MILK_SESSIONS[session]}"]
    for cow, liters in rows:
        details.append(f"№{cow.tag_number}" + (f" · {cow.name}" if cow.name else "") + f": {fmt(liters)} l")
    details.append(f"Jami: {fmt(total)} l ({len(rows)} ta sigir)")
    if len({cow.farm_id for cow, _ in rows}) > 1:
        details.append("Fermalar: " + ", ".join(sorted({cow.farm.name for cow, _ in rows})))
    return {'type': 'milk', 'data': {'records': records}, 'title': "🥛 Sut yozish", 'details': details}


def resolve_actions(user, raw_actions, today=None):
    """AI taklifini tekshiradi. (tayyor amallar ro'yxati, foydalanuvchiga aytiladigan muammolar) qaytaradi."""
    today = today or timezone.localdate()
    resolved, problems = [], []
    for raw in (raw_actions or [])[:MAX_ACTIONS]:
        if not isinstance(raw, dict) or raw.get('type') not in ALL_TYPES:
            continue
        if raw['type'] == 'milk':
            action = _resolve_milk(user, raw, today, problems)
            if action:
                resolved.append(action)
            continue
        if raw['type'] == 'finance':
            action, problem = _resolve_finance(user, raw, today)
        else:
            action, problem = _resolve_inventory(user, raw, today)
        if action:
            resolved.append(action)
        else:
            problems.append(problem)
    resolved = _drop_duplicate_purchases(resolved, problems)
    return resolved, problems


def _drop_duplicate_purchases(resolved, problems):
    """Omborga kirimning narxi o'zi moliyada «Chiqim» bo'ladi. AI xuddi shu xarid uchun alohida «finance»
    chiqim ham yozsa, balans ikki marta kamayadi: bunday takror chiqim olib tashlanadi."""
    paid = set()  # (ferma, summa) -- narxi bor ombor kirimlari
    for action in resolved:
        data = action['data']
        if action['type'] == 'inventory_add' and data.get('amount'):
            farm_id = InventoryItem.objects.filter(pk=data['inventory_item']).values_list('farm_id', flat=True).first()
            paid.add((farm_id, Decimal(data['amount'])))
    if not paid:
        return resolved

    kept = []
    for action in resolved:
        data = action['data']
        if (action['type'] == 'finance' and data['transaction_type'] == 'chiqim'
                and (data['farm'], Decimal(data['amount'])) in paid):
            problems.append(
                f"Takror chiqim yozilmadi ({money(Decimal(data['amount']))} so'm): ombor kirimining narxi "
                "moliyada o'zi chiqim bo'ladi."
            )
            continue
        kept.append(action)
    return kept


def create_proposal(user, raw_actions, today=None):
    """Tekshirilgan amallarni tasdiq kutuvchi yozuv qilib saqlaydi. (PendingAction yoki None, muammolar)."""
    resolved, problems = resolve_actions(user, raw_actions, today)
    if not resolved:
        return None, problems

    now = timezone.now()
    # Foydalanuvchida bir vaqtda faqat bitta kutilayotgan taklif: eskisi bekor bo'ladi
    PendingAction.objects.filter(user=user, status='kutilmoqda').update(status='bekor', resolved_at=now)
    PendingAction.objects.filter(
        user=user, created_at__lt=now - timedelta(days=KEEP_HISTORY_DAYS)
    ).exclude(status='kutilmoqda').delete()
    return PendingAction.objects.create(user=user, actions=resolved), problems


def serialize_proposal(pending):
    """Frontend uchun karta ma'lumoti."""
    return {
        'id': pending.pk,
        'expires_at': pending.expires_at.isoformat(),
        'items': [{'title': a['title'], 'details': a['details']} for a in pending.actions],
    }


# ---------------------------------------------------------------- bajarish

def _run_serializer(view_cls, serializer_cls, data, request):
    """Oddiy API'dagi perform_create() ni o'shanday ishlatadi (ruxsat, zaxira, Telegram bilan)."""
    view = view_cls()
    view.request = request
    view.format_kwarg = None
    serializer = serializer_cls(data=data, context={'request': request})
    serializer.is_valid(raise_exception=True)
    view.perform_create(serializer)
    return serializer.instance


def execute(request, pending):
    """Tasdiqlangan amallarni bajaradi (chaqiruvchi tranzaksiya ochgan bo'lishi kerak).
    Xato bo'lsa DRF istisnosi ko'tariladi va hammasi bekor qilinadi. Natija matnlari ro'yxatini qaytaradi."""
    results = []
    for action in pending.actions:
        if action['type'] == 'finance':
            tx = _run_serializer(TransactionViewSet, TransactionSerializer, action['data'], request)
            sign = "Chiqim" if tx.transaction_type == 'chiqim' else "Kirim"
            results.append(f"✅ {sign} yozildi: {money(tx.amount)} so'm ({tx.get_category_display()})")
        elif action['type'] == 'milk':
            records = action['data']['records']
            total = Decimal('0')
            for rec in records:
                milk = _run_serializer(MilkRecordViewSet, MilkRecordSerializer, rec, request)
                total += milk.liters
            first = records[0]
            results.append(
                f"✅ Sut yozildi: {len(records)} ta sigir, jami {fmt(total)} l "
                f"({MILK_SESSIONS[first['session']].lower()}, {parse_date(first['date']):%d.%m.%Y})"
            )
        elif action['type'] in INVENTORY_TYPES:
            rec = _run_serializer(InventoryTransactionViewSet, InventoryTransactionSerializer,
                                  action['data'], request)
            item = InventoryItem.objects.get(pk=rec.inventory_item_id)
            verb = "chiqarildi" if rec.transaction_type == 'sarf' else "kirim qilindi"
            low = " ⚠️ Zaxira kam qoldi!" if item.is_low_stock else ""
            paid = f" 💸 Moliyada chiqim yozildi: {money(rec.amount)} so'm." if rec.finance_transaction_id else ""
            results.append(
                f"✅ {item.item_name}: {fmt(rec.quantity)} {item.unit} {verb}. "
                f"Omborda qoldi: {fmt(item.quantity)} {item.unit}.{low}{paid}"
            )
        else:
            raise ValidationError({'detail': "Noma'lum amal turi."})
    return results


def confirm(request, pending):
    """Kutilayotgan taklifni bajaradi. (HTTP kodi, javob dict) qaytaradi; bajarish xatosi istisno sifatida chiqadi."""
    if pending.status == 'bajarildi':
        return 409, {'detail': "Bu amal allaqachon bajarilgan."}
    if pending.status == 'bekor':
        return 400, {'detail': "Bu amal bekor qilingan. AI dan qaytadan so'rang."}
    if pending.is_expired:
        pending.status = 'bekor'
        pending.resolved_at = timezone.now()
        pending.save(update_fields=['status', 'resolved_at'])
        return 400, {'detail': "Tasdiqlash muddati o'tdi. AI dan qaytadan so'rang."}

    with transaction.atomic():
        results = execute(request, pending)
        pending.status = 'bajarildi'
        pending.resolved_at = timezone.now()
        pending.save(update_fields=['status', 'resolved_at'])
    return 200, {'detail': "Bajarildi", 'results': results}
