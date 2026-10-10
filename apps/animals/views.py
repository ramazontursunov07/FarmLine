from django.db.models import Q
from rest_framework import viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated

from apps.farms.models import Worker
from apps.users.permissions import IsAppAdmin, is_app_admin
from .models import AnimalGroup, AnimalEvent, AnimalType
from .permissions import IsFarmOwnerOrWorker
from .serializers import AnimalTypeSerializer, AnimalGroupSerializer, AnimalEventSerializer


def is_farm_member(user, farm):
    """Ferma egasi yoki shu fermaga biriktirilgan ishchimi?"""
    return farm.owner_id == user.id or Worker.objects.filter(farm=farm, user=user).exists() #fermer bo'lsa yokida shu fermada ishchi bo'lsa


class AnimalTypeViewSet(viewsets.ModelViewSet):
    """Hayvon turlari umumiy. Ko'rish: hamma. Qo'shish: fermer/admin. O'zgartirish/o'chirish: admin."""
    queryset = AnimalType.objects.all().order_by('name')
    serializer_class = AnimalTypeSerializer

    def get_permissions(self):
        if self.action in ('update', 'partial_update', 'destroy'): #bu yerda shu amallarni bajarish faqat admin uchun ruxsat beriladi.
            return [IsAppAdmin()]
        return [IsAuthenticated()] #boshqa amallar authenticateddan o'tgan barcha.

    def perform_create(self, serializer):
        user = self.request.user
        if user.role not in ('fermer', 'admin') and not is_app_admin(user):
            raise PermissionDenied("Hayvon turini faqat fermer qo'sha oladi.")
        serializer.save()


class AnimalGroupViewSet(viewsets.ModelViewSet):
    """Hayvon guruhlari. Ko'rish: ferma egasi va ishchilar. Qo'shish/o'zgartirish/o'chirish: faqat ferma egasi."""
    queryset = AnimalGroup.objects.all()
    serializer_class = AnimalGroupSerializer
    permission_classes = [IsAuthenticated, IsFarmOwnerOrWorker] #Authenticateddan o'tgan,admin va ishchi bo'lsa ruxsat.

    def get_queryset(self):
        user = self.request.user
        qs = AnimalGroup.objects.select_related('animal_type', 'farm').filter(
            Q(farm__owner=user) | Q(farm__workers__user=user)
        ).distinct()
        p = self.request.query_params
        if p.get('farm', '').isdigit():
            qs = qs.filter(farm_id=int(p['farm']))
        if p.get('status'):
            qs = qs.filter(status=p['status'])
        return qs

    def _ensure_owner(self, farm):
        if farm.owner_id != self.request.user.id:
            raise PermissionDenied("Hayvon guruhlarini faqat ferma egasi boshqara oladi.")

    def perform_create(self, serializer):
        self._ensure_owner(serializer.validated_data['farm'])
        serializer.save()

    def perform_update(self, serializer):
        self._ensure_owner(serializer.instance.farm)
        serializer.save()

    def perform_destroy(self, instance):
        self._ensure_owner(instance.farm)
        instance.delete()


class AnimalEventViewSet(viewsets.ModelViewSet):
    """
    Ferma ishlari (kasallik, davolash, vaksinatsiya...). Ferma egasi ham, ishchi ham yoza oladi.
    Filtrlar: ?farm= ?animal_group= ?event_type= ?status= ?active=1 (yakunlanmaganlar)
    O'zgartirish/o'chirish: ferma egasi yoki yozuvni yozgan ishchining o'zi.
    """
    queryset = AnimalEvent.objects.all()
    serializer_class = AnimalEventSerializer
    permission_classes = [IsAuthenticated, IsFarmOwnerOrWorker]

    def get_queryset(self):
        user = self.request.user
        qs = AnimalEvent.objects.select_related(
            'animal_group__animal_type', 'animal_group__farm', 'recorded_by'
        ).filter(
            Q(animal_group__farm__owner=user) | Q(animal_group__farm__workers__user=user)
        ).distinct().order_by('-start_date', '-id')

        p = self.request.query_params
        if p.get('farm', '').isdigit():
            qs = qs.filter(animal_group__farm_id=int(p['farm']))
        if p.get('animal_group', '').isdigit():
            qs = qs.filter(animal_group_id=int(p['animal_group']))
        if p.get('event_type'):
            qs = qs.filter(event_type=p['event_type'])
        if p.get('status'):
            qs = qs.filter(status=p['status'])
        if p.get('active') in ('1', 'true'):
            qs = qs.exclude(status='yakunlangan')
        return qs

    def _ensure_can_modify(self, event):
        user = self.request.user
        if event.animal_group.farm.owner_id == user.id or event.recorded_by_id == user.id:
            return
        raise PermissionDenied("Bu yozuvni faqat ferma egasi yoki uni yozgan ishchi o'zgartira oladi.")

    def perform_create(self, serializer):
        group = serializer.validated_data['animal_group']
        if not is_farm_member(self.request.user, group.farm):
            raise PermissionDenied("Siz bu fermaga yozuv qo'sha olmaysiz.")
        serializer.save(recorded_by=self.request.user)

    def perform_update(self, serializer):
        event = serializer.instance
        self._ensure_can_modify(event)
        new_group = serializer.validated_data.get('animal_group')
        if new_group and new_group.farm_id != event.animal_group.farm_id:
            raise PermissionDenied("Yozuvni boshqa fermaga ko'chirib bo'lmaydi.")
        serializer.save()

    def perform_destroy(self, instance):
        self._ensure_can_modify(instance)
        instance.delete()
