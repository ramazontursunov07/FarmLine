"""
Kechki ish hisoboti: ferma egasiga ishchilar bugun nima qilgani bitta Telegram xabarida keladi.
Ishchining ishi "kim yozgani" (recorded_by / completed_by) bo'yicha topiladi.
"""
import logging
from collections import defaultdict
from decimal import Decimal

from django.conf import settings
from django.db.models import Sum
from django.utils import timezone

from apps.animals.models import AnimalEvent, MilkRecord, MilkSale
from apps.farms.models import Attendance, Farm
from apps.finance.models import Transaction
from apps.inventory.models import InventoryTransaction
from apps.tasks.models import Task

from .digest import MAX_ITEMS, money
from .models import User, WorkReportRun
from .telegram import send_message

logger = logging.getLogger(__name__)


def _name(user):
    return (user.get_full_name() or user.username) if user else "Noma'lum"


def _liters(value):
    return f"{Decimal(value or 0):.1f}".rstrip('0').rstrip('.')


def build_farm_work(farm, today):
    """Ferma bo'yicha: {ishchi_nomi: [qatorlar]} va kelmaganlar ro'yxati. Ish yo'q bo'lsa (None, [])."""
    worker_ids = set(farm.workers.values_list('user_id', flat=True))  # egasi emas, faqat ishchilar
    acts = defaultdict(list)

    def add(user, line):
        if user is not None and user.pk in worker_ids:
            acts[user].append(line)

    milk = defaultdict(lambda: [Decimal(0), 0])
    for r in (MilkRecord.objects.select_related('recorded_by')
            .filter(animal__farm=farm, created_at__date=today)):
        milk[r.recorded_by][0] += r.liters
        milk[r.recorded_by][1] += 1
    for user, (liters, cnt) in milk.items():
        add(user, f"🥛 Sog'ish: {_liters(liters)} l ({cnt} ta yozuv)")

    for t in Task.objects.select_related('completed_by').filter(
            farm=farm, status='bajarildi', completed_at__date=today):
        add(t.completed_by, f"✅ Vazifa bajarildi: {t.title}")

    for ev in (AnimalEvent.objects.select_related('recorded_by', 'animal_group__animal_type')
            .filter(animal_group__farm=farm, created_at__date=today)):
        add(ev.recorded_by, f"🩺 {ev.get_event_type_display()}: {ev.animal_group.animal_type.name} — {ev.title}")

    for tr in (InventoryTransaction.objects.select_related('recorded_by', 'inventory_item')
            .filter(inventory_item__farm=farm, created_at__date=today)):
        sign = "kirim" if tr.transaction_type == 'kirim' else "sarf"
        add(tr.recorded_by,
            f"📦 Ombor {sign}: {tr.inventory_item.item_name} {tr.quantity.normalize():f} {tr.inventory_item.unit}")

    for s in MilkSale.objects.select_related('recorded_by').filter(farm=farm, created_at__date=today):
        add(s.recorded_by, f"💵 Sut sotildi: {_liters(s.liters)} l — {money(s.amount)} so'm")

    for tx in Transaction.objects.select_related('recorded_by').filter(
            farm=farm, created_at__date=today, milk_sale__isnull=True, inventory_purchase__isnull=True):
        word = "kirim" if tx.transaction_type == 'kirim' else "chiqim"
        add(tx.recorded_by, f"💰 Moliya {word}: {money(tx.amount)} so'm")

    absent = list(Attendance.objects.select_related('worker__user').filter(
        worker__farm=farm, date=today, status='kelmadi'))
    return acts, [_name(a.worker.user) for a in absent]


def build_work_report(owner, today):
    """Egasi uchun kechki hisobot matni. Egasi fermasi bo'lmasa yoki fermada ishchi yo'q bo'lsa None."""
    sections = []
    for farm in Farm.objects.filter(owner=owner).order_by('name'):
        if not farm.workers.exists():
            continue
        acts, absent = build_farm_work(farm, today)
        lines = [f"🏡 {farm.name}"]
        if acts:
            for user in sorted(acts, key=_name):
                items = acts[user]
                lines.append(f"👤 {_name(user)}")
                lines += [f"  {x}" for x in items[:MAX_ITEMS * 2]]
                if len(items) > MAX_ITEMS * 2:
                    lines.append(f"  ... va yana {len(items) - MAX_ITEMS * 2} ta")
        else:
            lines.append("Bugun ishchilar hech narsa yozmadi.")
        if absent:
            lines.append(f"🚫 Kelmadi: {', '.join(absent)}")
        sections.append("\n".join(lines))
    if not sections:
        return None
    return f"🌙 FarmLine — bugun ishchilar ishi ({today:%d.%m.%Y})\n\n" + "\n\n".join(sections)


def send_work_reports(today):
    """Telegrami ulangan egalariga yuboradi. (yuborilgan, yuborilmagan) qaytaradi."""
    sent = skipped = 0
    owners = (User.objects.exclude(telegram_chat_id__isnull=True).exclude(telegram_chat_id='')
              .filter(owned_farms__isnull=False).distinct())
    for user in owners:
        text = build_work_report(user, today)
        if not text:
            continue
        if send_message(user.telegram_chat_id, text):
            sent += 1
        else:
            skipped += 1
    return sent, skipped


def send_due_work_report(now=None):
    """
    Ichki rejalashtiruvchi uchun: REPORT_HOUR kelgan va bugun yuborilmagan bo'lsa yuboradi.
    None — ish yo'q, True — yuborildi, False — xato (keyingi urinishda qayta).
    """
    now = timezone.localtime(now) if now else timezone.localtime()
    if now.hour < settings.REPORT_HOUR:
        return None
    today = now.date()
    run, created = WorkReportRun.objects.get_or_create(date=today)
    if not created:
        return None
    try:
        sent, skipped = send_work_reports(today)
        logger.info("Kechki ish hisoboti: %s ta yuborildi, %s ta yuborilmadi", sent, skipped)
        return True
    except Exception:
        logger.exception("Kechki ish hisobotini yuborib bo'lmadi")
        WorkReportRun.objects.filter(pk=run.pk).delete()
        return False
