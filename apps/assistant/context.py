"""AI yordamchiga beriladigan foydalanuvchi ma'lumoti (ferma holati).

Maxfiylik: fermer o'z fermalarini to'liq ko'radi; ishchi faqat o'z vazifalarini
(moliya yo'q); admin uchun hech narsa berilmaydi.
Hajm cheklangan: har bir ro'yxatdan eng ko'pi bilan MAX_ROWS ta qator olinadi.
"""
from datetime import timedelta

from django.db.models import Q, Sum
from django.utils import timezone

from apps.animals.models import AnimalEvent, AnimalGroup
from apps.farms.models import Farm
from apps.finance.models import Transaction
from apps.inventory.models import InventoryItem
from apps.tasks.models import Task
from apps.users.digest import build_worker_digest, money, qty

MAX_FARMS = 5
MAX_ROWS = 10


def _period(farm, start, end):
    row = Transaction.objects.filter(farm=farm, date__gte=start, date__lte=end).aggregate(
        income=Sum('amount', filter=Q(transaction_type='kirim')),
        expense=Sum('amount', filter=Q(transaction_type='chiqim')),
    )
    income, expense = row['income'] or 0, row['expense'] or 0
    return income, expense, income - expense


def _farm_context(farm, today):
    month_start = today.replace(day=1)
    prev_end = month_start - timedelta(days=1)
    prev_start = prev_end.replace(day=1)

    lines = [f"=== Ferma: {farm.name} ({farm.get_farm_type_display()}, {farm.location}) ==="]

    # Hayvonlar
    animals = (
        AnimalGroup.objects.filter(farm=farm, status='faol')
        .values('animal_type__name', 'breed')
        .annotate(total=Sum('count'))
        .order_by('-total')[:MAX_ROWS]
    )
    if animals:
        lines.append("Hayvonlar (faol): " + ", ".join(
            f"{a['animal_type__name']}{' (' + a['breed'] + ')' if a['breed'] else ''} — {a['total']} ta"
            for a in animals
        ))
    else:
        lines.append("Hayvonlar: kiritilmagan")

    # Moliya
    for label, (start, end) in (
        ("Bugun", (today, today)),
        (f"Shu oy ({month_start:%d.%m}–{today:%d.%m})", (month_start, today)),
        ("O'tgan oy", (prev_start, prev_end)),
    ):
        inc, exp, profit = _period(farm, start, end)
        word = "foyda" if profit >= 0 else "zarar"
        lines.append(f"{label}: kirim {money(inc)}, chiqim {money(exp)}, {word} {money(abs(profit))} so'm")

    top = (
        Transaction.objects.filter(farm=farm, transaction_type='chiqim', date__gte=month_start)
        .values('category').annotate(total=Sum('amount')).order_by('-total')[:5]
    )
    if top:
        names = dict(Transaction.CATEGORY_CHOICES)
        lines.append("Shu oy eng katta chiqimlar: " + ", ".join(
            f"{names.get(t['category'], t['category'])} {money(t['total'])}" for t in top
        ))

    recent = Transaction.objects.filter(farm=farm).order_by('-date', '-id')[:5]
    if recent:
        lines.append("Oxirgi kirim-chiqimlar:")
        for t in recent:
            lines.append(
                f"  • {t.date:%d.%m.%Y} {t.get_transaction_type_display()} {money(t.amount)} so'm "
                f"({t.get_category_display()}){': ' + t.description[:60] if t.description else ''}"
            )

    # Ombor
    items = list(InventoryItem.objects.filter(farm=farm).order_by('item_name')[:MAX_ROWS * 2])
    if items:
        lines.append("Ombor:")
        for it in items:
            low = " (KAM QOLGAN!)" if it.quantity <= it.low_stock_threshold else ""
            lines.append(f"  • {it.item_name}: {qty(it.quantity)} {it.unit}{low}")

    # Davolanayotgan hayvonlar
    sick = list(
        AnimalEvent.objects.select_related('animal_group__animal_type')
        .filter(animal_group__farm=farm, event_type__in=('kasallik', 'davolash'))
        .exclude(status='yakunlangan').order_by('start_date')[:MAX_ROWS]
    )
    if sick:
        lines.append("Davolanayotganlar:")
        for ev in sick:
            lines.append(f"  • {ev.animal_group.animal_type.name}: {ev.title} ({ev.days_since_start} kun)")

    # Vazifalar va ishchilar
    open_tasks = Task.objects.filter(farm=farm).exclude(status='bajarildi')
    overdue = open_tasks.filter(due_date__lt=today).count()
    lines.append(f"Ochiq vazifalar: {open_tasks.count()} ta (shundan muddati o'tgan: {overdue} ta)")
    for t in open_tasks.order_by('due_date', '-id')[:5]:
        due = f", muddat {t.due_date:%d.%m}" if t.due_date else ""
        lines.append(f"  • {t.title}{due}")
    workers = farm.workers.select_related('user').all()[:MAX_ROWS]
    if workers:
        lines.append("Ishchilar: " + ", ".join(w.user.get_full_name() or w.user.username for w in workers))

    return "\n".join(lines)


def build_context(user, today=None):
    today = today or timezone.localdate()
    if user.role == 'fermer':
        farms = Farm.objects.filter(owner=user).order_by('name')[:MAX_FARMS]
        return "\n\n".join(_farm_context(f, today) for f in farms)
    if user.role == 'ishchi':
        return build_worker_digest(user, today) or ''
    return ''
