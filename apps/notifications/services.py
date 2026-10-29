"""
Sayt ichidagi bildirishnomalar.

1. Hodisalar -- apps.users.notify.notify_users Telegramga yuborish bilan birga shu yerga ham yozadi.
2. Eslatmalar -- tug'ish, quritish, qarz va boshqalar (apps/users/alerts.py): foydalanuvchi bildirishnomalarni
   ochganda kuniga bir marta (dedupe_key bilan) hisoblanib yoziladi. Telegram ulanmagan foydalanuvchi ham oladi.
"""
import logging
from datetime import timedelta

from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import Notification

logger = logging.getLogger(__name__)

READ_KEEP_DAYS = 30  # o'qilganlar shuncha kundan keyin o'chiriladi
ANY_KEEP_DAYS = 90  # o'qilmagan bo'lsa ham shuncha kundan keyin o'chiriladi
SYNC_COOLDOWN = 600  # eslatmalar bir foydalanuvchi uchun ko'pi bilan 10 daqiqada bir marta qayta hisoblanadi
TITLE_MAX = 200


def create(users, kind, title, body='', link='', dedupe_key=''):
    """Har bir foydalanuvchiga bitta bildirishnoma. dedupe_key bir xil bo'lsa, takror yozilmaydi."""
    created = []
    seen = set()
    for user in users:
        if user is None or user.pk in seen:
            continue
        seen.add(user.pk)
        data = dict(kind=kind, title=title[:TITLE_MAX], body=body, link=link)
        if not dedupe_key:
            created.append(Notification.objects.create(user=user, **data))
            continue
        try:
            with transaction.atomic():
                obj, is_new = Notification.objects.get_or_create(user=user, dedupe_key=dedupe_key, defaults=data)
        except IntegrityError:  # ikki so'rov bir vaqtda yozmoqchi bo'ldi
            continue
        if is_new:
            created.append(obj)
    return created


def from_text(users, text, kind='event', link=''):
    """Telegram matnidan: birinchi qator sarlavha, qolgani matn."""
    lines = [ln for ln in str(text).strip().splitlines()]
    if not lines:
        return []
    return create(users, kind, lines[0].strip(), "\n".join(lines[1:]).strip(), link)


def _alert_builders():
    from apps.users import alerts
    # (kind, builder, sahifa, ishchiga ham ko'rsatiladimi)
    return [
        ('calving', alerts.calving_lines, 'animals', True),
        ('dry_off', alerts.dry_off_lines, 'animals', True),
        ('rebreed', alerts.rebreed_lines, 'animals', False),
        ('debt', alerts.debt_lines, 'debts', False),
        ('withdrawal', alerts.withdrawal_lines, 'animals', False),
        ('vaccination', alerts.vaccination_lines, 'animals', False),
        ('feed', alerts.feed_forecast_lines, 'inventory', False),
        ('spending', alerts.spending_alert_lines, 'finance', False),
    ]


def sync_alerts(user, today=None):
    """Foydalanuvchi fermalari bo'yicha bugungi eslatmalarni bildirishnomaga yozadi. Yangi yozilganlar sonini qaytaradi."""
    from apps.farms.models import Farm
    today = today or timezone.localdate()
    cache_key = f'notif-sync:{user.pk}:{today}'
    if cache.get(cache_key):
        return 0
    cache.set(cache_key, 1, SYNC_COOLDOWN)

    farms = {f.pk: (f, True) for f in Farm.objects.filter(owner=user)}
    for f in Farm.objects.filter(workers__user=user).distinct():
        farms.setdefault(f.pk, (f, False))
    multi = len(farms) > 1

    new = 0
    for farm, is_owner in farms.values():
        for kind, builder, page, for_worker in _alert_builders():
            if not is_owner and not for_worker:
                continue
            try:
                lines = builder(farm, today)
            except Exception:
                logger.exception("Bildirishnoma eslatmasini hisoblashda xato: %s (ferma id=%s)", kind, farm.pk)
                continue
            if not lines:
                continue
            title = lines[0].strip()
            if multi:
                title = f"{title} — {farm.name}"
            body = "\n".join(ln.strip() for ln in lines[1:])
            new += len(create([user], kind, title, body, f'/farms/{farm.pk}/{page}',
                              dedupe_key=f'{kind}:{farm.pk}:{today.isoformat()}'))
    cleanup(user)
    return new


def cleanup(user):
    now = timezone.now()
    Notification.objects.filter(user=user, is_read=True, created_at__lt=now - timedelta(days=READ_KEEP_DAYS)).delete()
    Notification.objects.filter(user=user, created_at__lt=now - timedelta(days=ANY_KEEP_DAYS)).delete()
