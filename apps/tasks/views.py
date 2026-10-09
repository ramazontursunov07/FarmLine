from django.db.models import Q
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated

from .models import Task
from .serializers import TaskSerializer

# Ishchi faqat shu maydonlarni o'zgartira oladi
WORKER_EDITABLE = {'status', 'result_note'}


class TaskViewSet(viewsets.ModelViewSet):
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

    def perform_create(self, serializer):
        if not self._is_owner(serializer.validated_data['farm']):
            raise PermissionDenied("Vazifani faqat ferma egasi qo'sha oladi.")
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        task = serializer.instance
        if not self._is_owner(task.farm):
            extra = set(self.request.data.keys()) - WORKER_EDITABLE
            if extra:
                raise PermissionDenied("Ishchi faqat vazifa holati va izohini o'zgartira oladi.")

        new_status = serializer.validated_data.get('status', task.status)
        extra_fields = {}
        if new_status == 'bajarildi' and task.status != 'bajarildi':
            extra_fields = {'completed_by': self.request.user, 'completed_at': timezone.now()}
        elif new_status != 'bajarildi' and task.status == 'bajarildi':
            extra_fields = {'completed_by': None, 'completed_at': None}
        serializer.save(**extra_fields)

    def perform_destroy(self, instance):
        if not self._is_owner(instance.farm):
            raise PermissionDenied("Vazifani faqat ferma egasi o'chira oladi.")
        instance.delete()
