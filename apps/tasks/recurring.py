"""
Takrorlanuvchi vazifalar: muddati kelganda oddiy vazifa (`Task`) yaratadi.

  * `create_due()` har kuni (rejalashtiruvchi yoki cron orqali) chaqiriladi va qayta chaqirilsa ham ikki marta yaratmaydi;
  * server o'chiq bo'lib qolsa, o'tib ketgan davrlar uchun bitta (eng eski) vazifa yaratiladi, qolganlari o'tkazib yuboriladi;
  * oy va yil bo'yicha takrorlashda sana qisqa oyga tushib qolsa, oyning oxirgi kuniga olinadi (31-yanvar -> 28-fevral).
"""
import calendar
import logging
from datetime import date, timedelta

from django.db import transaction
from django.utils import timezone

from .models import RecurringTask, Task

logger = logging.getLogger(__name__)


def add_months(d, months, anchor_day):
    index = d.year * 12 + (d.month - 1) + months
    year, month = divmod(index, 12)
    month += 1
    return date(year, month, min(anchor_day, calendar.monthrange(year, month)[1]))


def advance(rt, d):
    """`d` sanadan keyingi takrorlanish sanasi."""
    n = max(rt.interval, 1)
    if rt.frequency == 'kunlik':
        return d + timedelta(days=n)
    if rt.frequency == 'haftalik':
        return d + timedelta(weeks=n)
    if rt.frequency == 'oylik':
        return add_months(d, n, rt.anchor_day)
    return add_months(d, 12 * n, rt.anchor_day)  # yillik


def is_due(rt, today):
    lead = 0 if rt.frequency == 'kunlik' else rt.lead_days
    return rt.is_active and rt.next_due - timedelta(days=lead) <= today


def _notify(task):
    from apps.users.models import User
    from apps.users.notify import notify_users
    recipients = [task.assigned_to] if task.assigned_to_id else list(
        User.objects.filter(worker_profiles__farm=task.farm))
    lines = [f"📋 Vazifa ({task.farm.name}):", task.title]
    if task.due_date:
        lines.append(f"Muddat: {task.due_date:%d.%m.%Y}")
    lines.append("🔁 Takrorlanuvchi vazifa")
    notify_users(recipients, "\n".join(lines))


def fire(rt, today):
    """Bitta takrorlanuvchi vazifa uchun oddiy vazifa yaratadi. Yaratilsa, Task qaytaradi."""
    due = rt.next_due
    upcoming = advance(rt, due)
    while upcoming < today:  # o'tib ketgan davrlarni o'tkazib yuboramiz
        upcoming = advance(rt, upcoming)
    with transaction.atomic():
        # Ikki jarayon bir vaqtda ishlasa ham vazifa bir marta yaratiladi
        moved = RecurringTask.objects.filter(pk=rt.pk, next_due=due, is_active=True).update(
            next_due=upcoming, last_created_at=timezone.now())
        if not moved:
            return None
        task = Task.objects.create(
            farm=rt.farm, title=rt.title, description=rt.description, assigned_to=rt.assigned_to,
            due_date=due, priority=rt.priority, created_by=rt.created_by or rt.farm.owner,
        )
    _notify(task)
    return task


def create_due(today=None):
    today = today or timezone.localdate()
    created = []
    for rt in RecurringTask.objects.filter(is_active=True, next_due__lte=today + timedelta(days=60)
                                           ).select_related('farm__owner', 'assigned_to', 'created_by'):
        if is_due(rt, today):
            try:
                task = fire(rt, today)
            except Exception:
                logger.exception("Takrorlanuvchi vazifani yaratib bo'lmadi (id=%s)", rt.pk)
                continue
            if task is not None:
                created.append(task)
    return created


# Rejalashtiruvchi har daqiqa chaqirgani uchun, bazaga kuniga bir martagina murojaat qilamiz
_last_run = None


def create_due_once_a_day():
    global _last_run
    today = timezone.localdate()
    if _last_run == today:
        return []
    created = create_due(today)
    _last_run = today
    return created
