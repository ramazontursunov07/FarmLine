from datetime import timedelta

from django.db.models import F, Q, Sum
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.animals.models import AnimalEvent, AnimalGroup
from apps.animals.serializers import AnimalEventSerializer
from apps.finance.models import Transaction
from apps.inventory.models import InventoryItem, InventoryTransaction
from apps.inventory.serializers import InventoryItemSerializer
from apps.tasks.models import Task
from apps.tasks.serializers import TaskSerializer
from apps.users.permissions import is_app_admin
from .models import Farm, Worker
from .serializers import FarmSerializer, WorkerCreateSerializer, WorkerSerializer


class WorkerViewSet(viewsets.ModelViewSet):
    """
    Ishchilar. Faqat ferma egasi ishchi qo'sha, tahrirlay va olib tashlay oladi.
    Ishchining o'zi faqat o'z yozuvini ko'ra oladi. ?farm=<id> bilan filtrlanadi.
    """
    queryset = Worker.objects.all()
    serializer_class = WorkerSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = Worker.objects.select_related('user', 'farm').filter(
            Q(farm__owner=user) | Q(user=user)
        ).distinct()
        farm_id = self.request.query_params.get('farm')
        if farm_id and farm_id.isdigit():
            qs = qs.filter(farm_id=int(farm_id))
        return qs

    def create(self, request, *args, **kwargs):
        serializer = WorkerCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        farm = serializer.validated_data['farm']
        if farm.owner != request.user:
            raise PermissionDenied("Siz faqat o'zingizning fermangizga ishchi qo'sha olasiz.")

        worker = serializer.save()
        data = WorkerSerializer(worker, context=self.get_serializer_context()).data
        return Response(data, status=status.HTTP_201_CREATED)

    def _ensure_owner(self, worker):
        if worker.farm.owner != self.request.user:
            raise PermissionDenied("Faqat ferma egasi ishchini o'zgartira yoki olib tashlay oladi.")

    def perform_update(self, serializer):
        self._ensure_owner(serializer.instance)
        serializer.save()

    def perform_destroy(self, instance):
        self._ensure_owner(instance)
        user = instance.user
        instance.delete()
        # Ishchi boshqa hech qaysi fermada qolmagan bo'lsa, akkaunt bloklanadi
        # (o'chirilmaydi, shunda uning yozgan kirim-chiqim tarixi saqlanib qoladi).
        if user.role == 'ishchi' and not user.worker_profiles.exists():
            user.is_active = False
            user.save(update_fields=['is_active'])


class FarmViewSet(viewsets.ModelViewSet):
    queryset = Farm.objects.all()
    serializer_class = FarmSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if is_app_admin(user):
            return Farm.objects.select_related('owner').all()
        return Farm.objects.select_related('owner').filter(
            Q(owner=user) | Q(workers__user=user)
        ).distinct()

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    # --- faqat ferma egasi tahrirlay va o'chira oladi (ishchi va admin faqat ko'radi) ---
    def _ensure_owner(self, farm):
        if farm.owner != self.request.user:
            raise PermissionDenied("Faqat ferma egasi uni o'zgartira yoki o'chira oladi.")

    def perform_update(self, serializer):
        self._ensure_owner(serializer.instance)
        serializer.save()

    def perform_destroy(self, instance):
        self._ensure_owner(instance)
        instance.delete()

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """
        Fermer uchun bosh panel: o'z fermalari bo'yicha umumiy ko'rsatkichlar.
        ?farm=<id> bilan bitta fermaga cheklash mumkin.
        """
        user = request.user
        owned = Farm.objects.filter(owner=user).order_by('name')
        farms_list = [{'id': f.id, 'name': f.name} for f in owned]

        farm_param = request.query_params.get('farm', '')
        farms = owned.filter(id=int(farm_param)) if farm_param.isdigit() else owned
        ids = list(farms.values_list('id', flat=True))

        today = timezone.localdate()

        # --- Hayvonlar ---
        groups = AnimalGroup.objects.filter(farm_id__in=ids, status='faol')
        by_type = list(
            groups.values('animal_type__name').annotate(total=Sum('count')).order_by('-total')
        )
        animals = {
            'total': groups.aggregate(t=Sum('count'))['t'] or 0,
            'by_type': [{'name': r['animal_type__name'], 'count': r['total']} for r in by_type],
        }

        # --- Davolanayotganlar ---
        treating = (
            AnimalEvent.objects.filter(
                animal_group__farm_id__in=ids, event_type__in=('kasallik', 'davolash')
            )
            .exclude(status='yakunlangan')
            .select_related('animal_group__animal_type', 'animal_group__farm', 'recorded_by')
            .order_by('start_date', 'id')
        )
        treatments = {
            'count': treating.count(),
            'items': AnimalEventSerializer(treating[:5], many=True).data,
        }

        # --- Vazifalar ---
        open_tasks = Task.objects.filter(farm_id__in=ids).exclude(status='bajarildi')
        overdue_qs = (
            open_tasks.filter(due_date__lt=today)
            .select_related('farm', 'assigned_to', 'created_by', 'completed_by')
            .order_by('due_date')
        )
        tasks = {
            'open': open_tasks.count(),
            'overdue': overdue_qs.count(),
            'overdue_items': TaskSerializer(overdue_qs[:5], many=True).data,
        }

        # --- Ombor ---
        low_qs = (
            InventoryItem.objects.filter(farm_id__in=ids, quantity__lte=F('low_stock_threshold'))
            .select_related('farm')
            .order_by('quantity')
        )
        inventory = {
            'low_count': low_qs.count(),
            'items': InventoryItemSerializer(low_qs[:5], many=True).data,
        }

        # --- Moliya: shu oy va o'tgan oy ---
        month_start = today.replace(day=1)
        next_start = (month_start + timedelta(days=32)).replace(day=1)
        prev_start = (month_start - timedelta(days=1)).replace(day=1)

        def totals(qs):
            agg = qs.aggregate(
                income=Sum('amount', filter=Q(transaction_type='kirim')),
                expense=Sum('amount', filter=Q(transaction_type='chiqim')),
            )
            income, expense = agg['income'] or 0, agg['expense'] or 0
            return {'income': income, 'expense': expense, 'profit': income - expense}

        base = Transaction.objects.filter(farm_id__in=ids)
        finance = {
            'month': totals(base.filter(date__gte=month_start, date__lt=next_start)),
            'previous': totals(base.filter(date__gte=prev_start, date__lt=month_start)),
        }

        # --- Ishchilarning oxirgi ishlari (ferma egasining o'zi yozganlari kirmaydi) ---
        def who(u):
            return u.get_full_name() or u.username

        activity = []
        for e in (
                AnimalEvent.objects.filter(animal_group__farm_id__in=ids, recorded_by__isnull=False)
                        .exclude(recorded_by=user)
                        .select_related('animal_group', 'recorded_by')
                        .order_by('-created_at')[:10]
        ):
            activity.append({
                'type': 'event', 'farm': e.animal_group.farm_id, 'at': e.created_at,
                'who': who(e.recorded_by), 'text': f"{e.get_event_type_display()}: {e.title}",
            })
        for t in (
                Task.objects.filter(farm_id__in=ids, status='bajarildi', completed_by__isnull=False)
                        .exclude(completed_by=user)
                        .select_related('completed_by')
                        .order_by('-completed_at')[:10]
        ):
            activity.append({
                'type': 'task', 'farm': t.farm_id, 'at': t.completed_at,
                'who': who(t.completed_by), 'text': f"Vazifa bajarildi: {t.title}",
            })
        for tr in (
                InventoryTransaction.objects.filter(inventory_item__farm_id__in=ids, recorded_by__isnull=False)
                        .exclude(recorded_by=user)
                        .select_related('inventory_item', 'recorded_by')
                        .order_by('-created_at')[:10]
        ):
            item = tr.inventory_item
            activity.append({
                'type': 'inventory', 'farm': item.farm_id, 'at': tr.created_at,
                'who': who(tr.recorded_by),
                'text': f"Ombor, {tr.get_transaction_type_display().lower()}: "
                        f"{format(tr.quantity.normalize(), 'f')} {item.unit} {item.item_name}",
            })
        activity.sort(key=lambda a: a['at'], reverse=True)

        return Response({
            'farms': farms_list,
            'farms_count': len(ids),
            'animals': animals,
            'treatments': treatments,
            'tasks': tasks,
            'inventory': inventory,
            'finance': finance,
            'activity': activity[:8],
        })
