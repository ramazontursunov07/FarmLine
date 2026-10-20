from datetime import date, timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Count, OuterRef, Q, Subquery, Sum
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.core.mixins import IdempotentCreateMixin
from apps.farms.models import Farm, Worker
from apps.users.notify import display_name, notify_users
from apps.users.permissions import IsAppAdmin, is_app_admin
from .models import COUNT_EVENT_TYPES, Animal, AnimalGroup, AnimalEvent, AnimalType, MilkRecord, WeightRecord
from .permissions import IsFarmOwnerOrWorker
from .serializers import (AnimalTypeSerializer, AnimalGroupSerializer, AnimalEventSerializer,
                          AnimalSerializer, WeightRecordSerializer, MilkRecordSerializer)


def one_decimal(value):
    """SQLite 15, PostgreSQL 15.0 qaytaradi: javobda har doim 1 ta kasr raqami bilan ('15.0')."""
    return str(Decimal(value).quantize(Decimal('0.1')))


def is_farm_member(user, farm):
    """Ferma egasi yoki shu fermaga biriktirilgan ishchimi?"""
    return farm.owner_id == user.id or Worker.objects.filter(farm=farm,
                                                             user=user).exists()  # fermer bo'lsa yokida shu fermada ishchi bo'lsa


class AnimalTypeViewSet(IdempotentCreateMixin, viewsets.ModelViewSet):
    """Hayvon turlari umumiy. Ko'rish: hamma. Qo'shish: fermer/admin. O'zgartirish/o'chirish: admin."""
    queryset = AnimalType.objects.all().order_by('name')
    serializer_class = AnimalTypeSerializer

    def get_permissions(self):
        if self.action in ('update', 'partial_update',
                           'destroy'):  # bu yerda shu amallarni bajarish faqat admin uchun ruxsat beriladi.
            return [IsAppAdmin()]
        return [IsAuthenticated()]  # boshqa amallar authenticateddan o'tgan barcha.

    def perform_create(self, serializer):
        user = self.request.user
        if user.role not in ('fermer', 'admin') and not is_app_admin(user):
            raise PermissionDenied("Hayvon turini faqat fermer qo'sha oladi.")
        serializer.save()


class AnimalGroupViewSet(IdempotentCreateMixin, viewsets.ModelViewSet):
    """Hayvon guruhlari. Ko'rish: ferma egasi va ishchilar. Qo'shish/o'zgartirish/o'chirish: faqat ferma egasi."""
    queryset = AnimalGroup.objects.all()
    serializer_class = AnimalGroupSerializer
    permission_classes = [IsAuthenticated,
                          IsFarmOwnerOrWorker]  # Authenticateddan o'tgan,admin va ishchi bo'lsa ruxsat.

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
        new_count = serializer.validated_data.get('count')
        if new_count is not None:
            cards = Animal.objects.filter(group=serializer.instance, status='faol').count()
            if new_count < cards:
                raise ValidationError({'count': f"Guruhda {cards} ta faol hayvon kartochkasi bor, "
                                                f"soni undan kam bo'lishi mumkin emas"})
        serializer.save()

    def perform_destroy(self, instance):
        self._ensure_owner(instance.farm)
        instance.delete()


class AnimalEventViewSet(IdempotentCreateMixin, viewsets.ModelViewSet):
    """
    Ferma ishlari (kasallik, davolash, vaksinatsiya...). Ferma egasi ham, ishchi ham yoza oladi.
    Filtrlar: ?farm= ?animal_group= ?animal= ?event_type= ?status= ?active=1 (yakunlanmaganlar)
    O'zgartirish/o'chirish: ferma egasi yoki yozuvni yozgan ishchining o'zi.
    """
    queryset = AnimalEvent.objects.all()
    serializer_class = AnimalEventSerializer
    permission_classes = [IsAuthenticated, IsFarmOwnerOrWorker]

    def get_queryset(self):
        user = self.request.user
        qs = AnimalEvent.objects.select_related(
            'animal_group__animal_type', 'animal_group__farm', 'recorded_by', 'animal'
        ).filter(
            Q(animal_group__farm__owner=user) | Q(animal_group__farm__workers__user=user)
        ).distinct().order_by('-start_date', '-id')

        p = self.request.query_params
        if p.get('farm', '').isdigit():
            qs = qs.filter(animal_group__farm_id=int(p['farm']))
        if p.get('animal_group', '').isdigit():
            qs = qs.filter(animal_group_id=int(p['animal_group']))
        if p.get('animal', '').isdigit():
            qs = qs.filter(animal_id=int(p['animal']))
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
        user = self.request.user
        group = serializer.validated_data['animal_group']
        if not is_farm_member(user, group.farm):
            raise PermissionDenied("Siz bu fermaga yozuv qo'sha olmaysiz.")

        # Tug'ilish bilan birga buzoq kartochkalarini ochish (kartochkalarni faqat ferma egasi boshqaradi)
        calves = serializer.validated_data.get('calves') or []
        if calves and group.farm.owner_id != user.id:
            raise PermissionDenied("Buzoq kartochkalarini faqat ferma egasi ochadi. "
                                   "Tug'ilishni kartochkasiz yozing.")

        event_type = serializer.validated_data['event_type']
        if event_type not in COUNT_EVENT_TYPES:
            serializer.save(recorded_by=user)
            return

        # O'lim/tug'ilish: guruh soni avtomatik yangilanadi (sotuvdagi kabi, qulflab)
        count = serializer.validated_data['animal_count']
        with transaction.atomic():
            locked = AnimalGroup.objects.select_for_update().get(pk=group.pk)
            if event_type == 'olim':
                if count > locked.count:
                    raise ValidationError({'animal_count': f"Guruhda faqat {locked.count} ta hayvon bor"})
                locked.count -= count
                if locked.count == 0:
                    locked.status = 'olgan'
                animal = serializer.validated_data.get('animal')
                active_cards = Animal.objects.filter(group=locked, status='faol').count()
                if animal is not None:
                    animal = Animal.objects.select_for_update().get(pk=animal.pk)
                    if animal.status != 'faol':
                        raise ValidationError({'animal': "Faqat faol hayvon uchun o'lim yozish mumkin"})
                    active_cards -= 1
                if locked.count < active_cards:
                    raise ValidationError({'animal_count': (
                        "Guruhda qolgan sondan ko'p faol hayvon kartochkasi bor. "
                        "Avval o'lgan hayvonning o'zini tanlab o'lim yozing.")})
            else:
                if locked.status != 'faol':
                    raise ValidationError({'animal_group': "Faol bo'lmagan guruhga tug'ilish yozib bo'lmaydi"})
                locked.count += count
            locked.save(update_fields=['count', 'status', 'updated_at'])
            event = serializer.save(recorded_by=user)
            if event_type == 'olim' and animal is not None:
                animal.status = 'olgan'
                animal.save(update_fields=['status', 'updated_at'])
            if event_type == 'tugilish' and calves:
                event._calves_created = self._create_calves(event, locked, calves)
            if event_type == 'tugilish' and serializer.validated_data.get('animal') is not None:
                # Ona tug'di: bug'ozlik tugaydi
                Animal.objects.filter(pk=serializer.validated_data['animal'].pk).update(
                    pregnant_since=None, due_date=None)

            if event_type == 'olim' and user.id != group.farm.owner_id:
                notify_users([group.farm.owner], (
                    f"⚠️ O'lim yozildi ({group.farm.name}):\n"
                    f"{group.animal_type.name}: {count} ta\n"
                    f"Guruhda qoldi: {locked.count} ta\n"
                    f"Kim: {display_name(user)}"
                ))

    @staticmethod
    def _create_calves(event, group, calves):
        """Tug'ilish yozuvi bilan bir tranzaksiyada buzoq kartochkalarini ochadi (guruh allaqachon qulflangan)."""
        try:
            created = [
                Animal.objects.create(
                    farm_id=group.farm_id, group=group, tag_number=c['tag_number'], name=c.get('name', ''),
                    sex=c.get('sex', 'urgochi'), birth_date=event.start_date, mother=event.animal, status='faol')
                for c in calves
            ]
        except IntegrityError:  # bir vaqtda boshqa so'rov shu quloq raqamini band qilgan bo'lsa
            raise ValidationError({'calves': "Bu quloq raqami fermada allaqachon bor"})
        if Animal.objects.filter(group=group, status='faol').count() > group.count:
            raise ValidationError({'calves': "Faol kartochkalar soni guruh sonidan oshib ketadi"})
        return created

    def perform_update(self, serializer):
        event = serializer.instance
        self._ensure_can_modify(event)
        data = serializer.validated_data
        if event.event_type in COUNT_EVENT_TYPES or data.get('event_type') in COUNT_EVENT_TYPES:
            for field in ('event_type', 'animal_group', 'animal_count', 'animal'):
                if field in data and data[field] != getattr(event, field):
                    raise ValidationError(
                        "O'lim va tug'ilish yozuvining turi, guruhi va sonini o'zgartirib bo'lmaydi. "
                        "Uni o'chirib, qaytadan kiriting.")
        new_group = serializer.validated_data.get('animal_group')
        if new_group and new_group.farm_id != event.animal_group.farm_id:
            raise PermissionDenied("Yozuvni boshqa fermaga ko'chirib bo'lmaydi.")
        serializer.save()

    def perform_destroy(self, instance):
        self._ensure_can_modify(instance)
        # Eski yozuvlarda (animal_count yo'q) guruh soniga ta'sir bo'lmagan, shuning uchun qaytariladigan narsa ham yo'q
        if instance.event_type not in COUNT_EVENT_TYPES or not instance.animal_count:
            instance.delete()
            return

        with transaction.atomic():
            locked = AnimalGroup.objects.select_for_update().get(pk=instance.animal_group_id)
            if instance.event_type == 'olim':
                locked.count += instance.animal_count  # o'lgan hayvonlar guruhga qaytadi
            else:
                if instance.animal_count > locked.count:
                    raise ValidationError(
                        "Bu tug'ilishni o'chirib bo'lmaydi: undan keyin hayvonlar kamaygan, soni yetmay qoladi.")
                locked.count -= instance.animal_count
                cards = Animal.objects.filter(group=locked, status='faol').count()
                if locked.count < cards:
                    raise ValidationError(
                        f"Bu tug'ilishni o'chirib bo'lmaydi: guruhda {cards} ta faol hayvon kartochkasi bor, "
                        f"o'chirgandan keyin guruh soni ({locked.count} ta) undan kam bo'lib qoladi. "
                        f"Avval buzoq kartochkasini o'chiring.")
            if locked.count > 0 and locked.status in ('olgan', 'sotilgan'):
                locked.status = 'faol'
            locked.save(update_fields=['count', 'status', 'updated_at'])
            if instance.event_type == 'olim' and instance.animal_id:
                # o'lgan deb belgilangan hayvon kartochkasi ham qaytadi
                Animal.objects.filter(pk=instance.animal_id, status='olgan').update(
                    status='faol', updated_at=timezone.now())
            instance.delete()


class AnimalViewSet(IdempotentCreateMixin, viewsets.ModelViewSet):
    """
    Alohida hayvon kartochkalari (ixtiyoriy; guruh soni `AnimalGroup.count` da qoladi).
    Ko'rish: ferma egasi va ishchilar. Qo'shish/o'zgartirish/o'chirish: faqat ferma egasi.
    Filtrlar: ?farm= ?group= ?status= ?sex= ?search= (quloq raqami yoki laqab)
    To'liq kartochka: GET /animals-card/{id}/card/
    """
    queryset = Animal.objects.all()
    serializer_class = AnimalSerializer
    permission_classes = [IsAuthenticated, IsFarmOwnerOrWorker]

    def get_queryset(self):
        user = self.request.user
        last_weight = WeightRecord.objects.filter(animal=OuterRef('pk')).order_by('-date', '-id')
        last_calving = AnimalEvent.objects.filter(
            animal=OuterRef('pk'), event_type='tugilish').order_by('-start_date', '-id')
        qs = (
            Animal.objects.select_related('group__animal_type', 'farm', 'mother')
            .filter(Q(farm__owner=user) | Q(farm__workers__user=user)).distinct()
            .annotate(
                last_weight=Subquery(last_weight.values('weight_kg')[:1]),
                last_weight_date=Subquery(last_weight.values('date')[:1]),
                last_calving_date=Subquery(last_calving.values('start_date')[:1]),
            )
        )
        p = self.request.query_params
        if p.get('farm', '').isdigit():
            qs = qs.filter(farm_id=int(p['farm']))
        if p.get('group', '').isdigit():
            qs = qs.filter(group_id=int(p['group']))
        if p.get('status'):
            qs = qs.filter(status=p['status'])
        if p.get('sex'):
            qs = qs.filter(sex=p['sex'])
        if p.get('search'):
            qs = qs.filter(Q(tag_number__icontains=p['search']) | Q(name__icontains=p['search']))
        return qs

    def _ensure_owner(self, farm):
        if farm.owner_id != self.request.user.id:
            raise PermissionDenied("Hayvon kartochkalarini faqat ferma egasi boshqara oladi.")

    @staticmethod
    def _check_capacity(group_id, exclude_pk=None):
        """Guruh qulflanadi; faol kartochkalar soni guruh sonidan oshsa, guruh soni oshiriladi."""
        group = AnimalGroup.objects.select_for_update().get(pk=group_id)
        if group.status != 'faol':
            raise ValidationError({'group': "Faol bo'lmagan guruhga kartochka qo'shib bo'lmaydi"})
        cards = Animal.objects.filter(group=group, status='faol')
        if exclude_pk:
            cards = cards.exclude(pk=exclude_pk)
        needed = cards.count() + 1
        if needed > group.count:
            # Yangi hayvon kartochkasi guruh sonini o'zi oshiradi (guruhni sonsiz ochish mumkin)
            group.count = needed
            group.save(update_fields=['count', 'updated_at'])

    def perform_create(self, serializer):
        group = serializer.validated_data['group']
        self._ensure_owner(group.farm)
        with transaction.atomic():
            if serializer.validated_data.get('status', 'faol') == 'faol':
                self._check_capacity(group.pk)
            serializer.save(farm=group.farm)

    def perform_update(self, serializer):
        animal = serializer.instance
        self._ensure_owner(animal.farm)
        data = serializer.validated_data
        new_group = data.get('group', animal.group)
        new_status = data.get('status', animal.status)
        if new_status != animal.status and 'olgan' in (new_status, animal.status):
            raise ValidationError({'status': (
                "O'lgan holatini o'zgartirish uchun o'lim voqeasidan foydalaning "
                "(animals-event, event_type=olim, animal=...): u guruh sonini ham yangilaydi.")})
        with transaction.atomic():
            if new_status == 'faol' and (new_group.pk != animal.group_id or animal.status != 'faol'):
                self._check_capacity(new_group.pk, exclude_pk=animal.pk)
            serializer.save()

    def perform_destroy(self, instance):
        self._ensure_owner(instance.farm)
        with transaction.atomic():
            # Faol hayvon o'chirilsa, guruhdagi hayvonlar soni ham 1 taga kamayadi.
            # Sotilgan/o'lgan hayvon soni avval (sotuv yoki o'lim yozuvida) kamaytirilgan, shuning uchun tegilmaydi.
            if instance.status == 'faol':
                group = AnimalGroup.objects.select_for_update().get(pk=instance.group_id)
                if group.count > 0:
                    group.count -= 1
                    group.save(update_fields=['count', 'updated_at'])
            instance.delete()

    @action(detail=True, methods=['get'])
    def card(self, request, pk=None):
        """Hayvonning to'liq kartochkasi: vazn tarixi, sut statistikasi, voqealar, buzoqlar."""
        animal = self.get_object()
        today = timezone.localdate()

        # --- vazn
        recent_weights = list(animal.weights.order_by('-date', '-id')[:100])
        weight_summary = {'last': None, 'last_date': None, 'previous': None, 'change_kg': None,
                          'daily_gain_g': None}
        if recent_weights:
            last = recent_weights[0]
            weight_summary.update(last=str(last.weight_kg), last_date=last.date)
            if len(recent_weights) > 1:
                prev = recent_weights[1]
                change = last.weight_kg - prev.weight_kg
                weight_summary.update(previous=str(prev.weight_kg), change_kg=str(change))
                days = (last.date - prev.date).days
                if days > 0:
                    weight_summary['daily_gain_g'] = int(change / days * 1000)
        weights = [{'id': w.id, 'date': w.date, 'weight_kg': str(w.weight_kg)} for w in reversed(recent_weights)]

        # --- sut (oxirgi 30 kun, kunlik jami)
        since = today - timedelta(days=29)
        daily = list(
            animal.milk_records.filter(date__gte=since).order_by()
            .values('date').annotate(total=Sum('liters')).order_by('date')
        )
        total = sum((row['total'] for row in daily), Decimal('0'))
        milk = {
            'period_days': 30,
            'days_recorded': len(daily),
            'total_liters': one_decimal(total),
            'daily_average': str((total / len(daily)).quantize(Decimal('0.1'))) if daily else None,
            'last_date': daily[-1]['date'] if daily else None,
            'last_day_liters': one_decimal(daily[-1]['total']) if daily else None,
            'daily': [{'date': row['date'], 'liters': one_decimal(row['total'])} for row in daily],
        }

        # --- voqealar va buzoqlar
        events = (
            AnimalEvent.objects.filter(animal=animal)
            .select_related('animal_group__animal_type', 'animal_group__farm', 'recorded_by', 'animal')
            .order_by('-start_date', '-id')[:20]
        )
        calves = list(animal.calves.values('id', 'tag_number', 'name', 'birth_date', 'status'))

        return Response({
            'animal': AnimalSerializer(animal, context=self.get_serializer_context()).data,
            'last_calving_date': animal.last_calving_date,
            'weight_summary': weight_summary,
            'weights': weights,
            'milk': milk,
            'events': AnimalEventSerializer(events, many=True, context=self.get_serializer_context()).data,
            'calves': calves,
        })


class _AnimalRecordViewSet(IdempotentCreateMixin, viewsets.ModelViewSet):
    """Vazn/sut yozuvlari uchun umumiy mantiq: ferma egasi va ishchi yozadi,
    o'zgartirish/o'chirish: ferma egasi yoki yozuvni yozgan ishchi."""
    model = None
    permission_classes = [IsAuthenticated, IsFarmOwnerOrWorker]

    def get_queryset(self):
        user = self.request.user
        qs = self.model.objects.select_related('animal', 'recorded_by').filter(
            Q(animal__farm__owner=user) | Q(animal__farm__workers__user=user)
        ).distinct().order_by('-date', '-id')
        p = self.request.query_params
        if p.get('farm', '').isdigit():
            qs = qs.filter(animal__farm_id=int(p['farm']))
        if p.get('animal', '').isdigit():
            qs = qs.filter(animal_id=int(p['animal']))
        for param, lookup in (('date_from', 'date__gte'), ('date_to', 'date__lte')):
            if p.get(param):
                value = parse_date(p[param])
                if value is None:
                    raise ValidationError({param: "Sana YYYY-MM-DD ko'rinishida bo'lishi kerak"})
                qs = qs.filter(**{lookup: value})
        return qs

    def _ensure_can_modify(self, record):
        user = self.request.user
        if record.animal.farm.owner_id == user.id or record.recorded_by_id == user.id:
            return
        raise PermissionDenied("Bu yozuvni faqat ferma egasi yoki uni yozgan ishchi o'zgartira oladi.")

    def perform_create(self, serializer):
        user = self.request.user
        animal = serializer.validated_data['animal']
        if not is_farm_member(user, animal.farm):
            raise PermissionDenied("Siz bu fermaga yozuv qo'sha olmaysiz.")
        serializer.save(recorded_by=user)

    def perform_update(self, serializer):
        self._ensure_can_modify(serializer.instance)
        serializer.save()

    def perform_destroy(self, instance):
        self._ensure_can_modify(instance)
        instance.delete()


class WeightRecordViewSet(_AnimalRecordViewSet):
    """Hayvon vazni. Filtrlar: ?farm= ?animal= ?date_from= ?date_to="""
    model = WeightRecord
    queryset = WeightRecord.objects.all()
    serializer_class = WeightRecordSerializer


class MilkRecordViewSet(_AnimalRecordViewSet):
    """Sut miqdori. Filtrlar: ?farm= ?animal= ?date_from= ?date_to="""
    model = MilkRecord
    queryset = MilkRecord.objects.all()
    serializer_class = MilkRecordSerializer

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """
        Sut hisoboti: tanlangan oyda har bir sigir va hamma sigirlar jami necha litr sut bergani,
        o'tgan oy bilan solishtirib. ?month=YYYY-MM (bo'lmasa, shu oy), ?farm= (bo'lmasa, barcha fermalar).
        """
        today = timezone.localdate()
        month = request.query_params.get('month') or f"{today:%Y-%m}"
        try:
            year, mon = (int(x) for x in month.split('-'))
            start = date(year, mon, 1)
        except (ValueError, TypeError):
            raise ValidationError({'month': "Oy YYYY-MM ko'rinishida bo'lishi kerak (masalan, 2026-10)"})
        next_start = date(year + (mon == 12), mon % 12 + 1, 1)
        prev_start = date(year - (mon == 1), (mon - 2) % 12 + 1, 1)

        # Ferma bo'yicha cheklash ichki so'rov (subquery) bilan: ishchilar jadvali bilan JOIN qilinsa,
        # bir nechta ishchi bor fermada har bir yozuv bir necha marta sanalib qolardi.
        user = request.user
        farms = Farm.objects.filter(Q(owner=user) | Q(workers__user=user)).values('pk')
        records = MilkRecord.objects.filter(animal__farm_id__in=farms)
        farm_id = request.query_params.get('farm', '')
        if farm_id:
            if not farm_id.isdigit():
                raise ValidationError({'farm': "Ferma raqami noto'g'ri"})
            records = records.filter(animal__farm_id=int(farm_id))

        in_month = Q(date__gte=start, date__lt=next_start)
        in_prev = Q(date__gte=prev_start, date__lt=start)
        rows = list(
            records.filter(date__gte=prev_start, date__lt=next_start).order_by()
            .values('animal_id', 'animal__tag_number', 'animal__name')
            # Annotatsiya nomi model maydoni bilan (liters) bir xil bo'lishi mumkin emas, shuning uchun month_/prev_
            .annotate(
                month_liters=Sum('liters', filter=in_month),
                prev_liters=Sum('liters', filter=in_prev),
                days=Count('date', filter=in_month, distinct=True),
            )
        )

        zero = Decimal('0')
        animals = []
        for row in rows:
            liters = row['month_liters'] or zero
            previous = row['prev_liters'] or zero
            days = row['days']
            animals.append({
                'animal': row['animal_id'],
                'tag_number': row['animal__tag_number'],
                'name': row['animal__name'],
                'liters': one_decimal(liters),
                'previous_liters': one_decimal(previous),
                'change': one_decimal(liters - previous),
                'days': days,
                'daily_average': one_decimal(liters / days) if days else None,
                '_sort': liters,
            })
        animals.sort(key=lambda a: (-a['_sort'], a['tag_number']))
        for a in animals:
            del a['_sort']

        total = sum((Decimal(a['liters']) for a in animals), zero)
        previous_total = sum((Decimal(a['previous_liters']) for a in animals), zero)
        return Response({
            'month': f"{start:%Y-%m}",
            'previous_month': f"{prev_start:%Y-%m}",
            'farm': int(farm_id) if farm_id else None,
            'total': one_decimal(total),
            'previous_total': one_decimal(previous_total),
            'change': one_decimal(total - previous_total),
            'animals_count': sum(1 for a in animals if Decimal(a['liters']) > 0),
            'animals': animals,
        })
