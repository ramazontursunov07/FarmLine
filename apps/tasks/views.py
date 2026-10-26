from django.db.models import Q
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated

from apps.core.mixins import IdempotentCreateMixin
from apps.users.models import User
from apps.users.notify import display_name, notify_users

from .models import RecurringTask, Task
from .serializers import RecurringTaskSerializer, TaskSerializer

# Ishchi faqat shu maydonlarni o'zgartira oladi
WORKER_EDITABLE = {'status', 'result_note'}


class TaskViewSet(IdempotentCreateMixin, viewsets.ModelViewSet):
    """
    Vazifalar.
    - Ferma egasi: o'z fermalaridagi hamma vazifani ko'radi, qo'shadi, tahrirlaydi, o'chiradi.
    - Ishchi: faqat o'ziga yoki "barcha ishchilarga" berilgan vazifalarni ko'radi
      va ularning holati (status) hamda izohini (result_note) o'zgartira oladi.
    Filtrlar: ?farm= ?status= ?assigned_to= ?open=1 (bajarilmaganlar)
    """
    queryset = Task.objects.all()
    serializer_class = TaskSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = Task.objects.select_related('farm', 'assigned_to', 'created_by', 'completed_by').filter(
            Q(farm__owner=user)
            | (Q(farm__workers__user=user) & (Q(assigned_to=user) | Q(assigned_to__isnull=True)))
        ).distinct()

        p = self.request.query_params
        if p.get('farm', '').isdigit():
            qs = qs.filter(farm_id=int(p['farm']))
        if p.get('status'):
            qs = qs.filter(status=p['status'])
        if p.get('assigned_to', '').isdigit():
            qs = qs.filter(assigned_to_id=int(p['assigned_to']))
        if p.get('open') in ('1', 'true'):
            qs = qs.exclude(status='bajarildi')
        return qs

    def _is_owner(self, farm):
        return farm.owner_id == self.request.user.id

    def _notify_assignee(self, task):
        """Vazifa berilgan ishchiga (yoki assigned_to bo'sh bo'lsa, fermaning hamma ishchilariga) xabar."""
        if task.assigned_to_id:
            recipients = [task.assigned_to]
        else:
            recipients = list(User.objects.filter(worker_profiles__farm=task.farm))
        lines = [f"📋 Yangi vazifa ({task.farm.name}):", task.title]
        if task.due_date:
            lines.append(f"Muddat: {task.due_date:%d.%m.%Y}")
        lines.append(f"Muhimlik: {task.get_priority_display()}")
        notify_users(recipients, "\n".join(lines))

    def perform_create(self, serializer):
        if not self._is_owner(serializer.validated_data['farm']):
            raise PermissionDenied("Vazifani faqat ferma egasi qo'sha oladi.")
        task = serializer.save(created_by=self.request.user)
        self._notify_assignee(task)

    def perform_update(self, serializer):
        task = serializer.instance
        if not self._is_owner(task.farm):
            extra = set(self.request.data.keys()) - WORKER_EDITABLE
            if extra:
                raise PermissionDenied("Ishchi faqat vazifa holati va izohini o'zgartira oladi.")

        old_status = task.status
        old_assignee = task.assigned_to_id
        new_status = serializer.validated_data.get('status', task.status)
        extra_fields = {}
        if new_status == 'bajarildi' and task.status != 'bajarildi':
            extra_fields = {'completed_by': self.request.user, 'completed_at': timezone.now()}
        elif new_status != 'bajarildi' and task.status == 'bajarildi':
            extra_fields = {'completed_by': None, 'completed_at': None}
        task = serializer.save(**extra_fields)

        user = self.request.user
        if task.assigned_to_id != old_assignee and task.assigned_to_id:
            self._notify_assignee(task)  # vazifa boshqa ishchiga o'tkazildi
        if new_status == 'bajarildi' and old_status != 'bajarildi' and not self._is_owner(task.farm):
            notify_users([task.farm.owner], (
                    f"✅ {display_name(user)} vazifani bajardi ({task.farm.name}):\n{task.title}"
                    + (f"\nIzoh: {task.result_note}" if task.result_note else "")
            ))

    def perform_destroy(self, instance):
        if not self._is_owner(instance.farm):
            raise PermissionDenied("Vazifani faqat ferma egasi o'chira oladi.")
        instance.delete()


class RecurringTaskViewSet(IdempotentCreateMixin, viewsets.ModelViewSet):
    """
    Takrorlanuvchi vazifalar (masalan, har yili vaksinatsiya). Faqat ferma egasi ko'radi va boshqaradi.
    Filtr: ?farm=
    """
    queryset = RecurringTask.objects.all()
    serializer_class = RecurringTaskSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = RecurringTask.objects.select_related('farm', 'assigned_to').filter(farm__owner=self.request.user)
        farm = self.request.query_params.get('farm', '')
        if farm.isdigit():
            qs = qs.filter(farm_id=int(farm))
        return qs

    def perform_create(self, serializer):
        if serializer.validated_data['farm'].owner_id != self.request.user.id:
            raise PermissionDenied("Takrorlanuvchi vazifani faqat ferma egasi qo'sha oladi.")
        serializer.save(created_by=self.request.user)
