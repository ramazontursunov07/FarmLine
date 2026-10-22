from datetime import timedelta
from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers

from .withdrawal import withdrawal_map
from .models import (COUNT_EVENT_TYPES, Animal, AnimalType, AnimalGroup, AnimalEvent, MilkRecord, MilkSale,
                     WeightRecord)


class AnimalTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnimalType
        fields = ['id', 'name']


class AnimalGroupSerializer(serializers.ModelSerializer):
    animal_type_name = serializers.CharField(source='animal_type.name', read_only=True)
    farm_name = serializers.CharField(source='farm.name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = AnimalGroup
        fields = ['id', 'farm', 'farm_name', 'animal_type', 'animal_type_name', 'breed', 'count',
                  'birth_date', 'status', 'status_display', 'created_at', 'updated_at']

    def update(self, instance, validated_data):
        validated_data.pop('farm', None)  # guruhni boshqa fermaga ko'chirib bo'lmaydi
        return super().update(instance, validated_data)


class CalfInputSerializer(serializers.Serializer):
    """Tug'ilish yozuvi bilan birga ochiladigan buzoq kartochkasi (Animal) ma'lumotlari."""
    tag_number = serializers.CharField(
        max_length=30, error_messages={'blank': "Quloq raqamini kiriting", 'required': "Quloq raqamini kiriting"})
    name = serializers.CharField(max_length=100, required=False, allow_blank=True, default='')
    sex = serializers.ChoiceField(choices=Animal.SEX_CHOICES, default='urgochi')


class AnimalEventSerializer(serializers.ModelSerializer):
    days_since_start = serializers.ReadOnlyField()
    recorded_by_username = serializers.CharField(source='recorded_by.username', read_only=True, default=None)
    recorded_by_name = serializers.SerializerMethodField()
    event_type_display = serializers.CharField(source='get_event_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    animal_group_label = serializers.SerializerMethodField()
    animal_group_count = serializers.IntegerField(source='animal_group.count', read_only=True)
    farm = serializers.IntegerField(source='animal_group.farm_id', read_only=True)
    animal_tag = serializers.CharField(source='animal.tag_number', read_only=True, default=None)
    # Tug'ilish bilan birga ochiladigan buzoq kartochkalari (faqat yozishda; ixtiyoriy)
    calves = CalfInputSerializer(many=True, write_only=True, required=False)
    calves_created = serializers.SerializerMethodField()
    newborn_cards = serializers.SerializerMethodField()
    medicine_name = serializers.CharField(source='medicine.item_name', read_only=True, default=None)
    withdrawal_until = serializers.SerializerMethodField()

    class Meta:
        model = AnimalEvent
        fields = ['id', 'farm', 'animal_group', 'animal_group_label', 'animal_group_count',
                  'animal', 'animal_tag', 'calves', 'calves_created', 'newborn_cards',
                  'event_type', 'event_type_display', 'animal_count', 'title', 'description',
                  'status', 'status_display', 'start_date', 'end_date',
                  'medicine', 'medicine_name', 'withdrawal_days', 'withdrawal_until',
                  'recorded_by', 'recorded_by_username', 'recorded_by_name',
                  'days_since_start', 'created_at', 'updated_at']
        read_only_fields = ['recorded_by', 'created_at', 'updated_at']

    def get_recorded_by_name(self, obj):
        user = obj.recorded_by
        if not user:
            return None
        return user.get_full_name() or user.username

    def get_animal_group_label(self, obj):
        group = obj.animal_group
        return f"{group.animal_type.name} ({group.breed})" if group.breed else group.animal_type.name

    def get_calves_created(self, obj):
        # View tug'ilishda ochilgan kartochkalarni `_calves_created` ga qo'yadi; boshqa yozuvlarda bo'sh
        return [{'id': a.id, 'tag_number': a.tag_number} for a in getattr(obj, '_calves_created', [])]

    def get_withdrawal_until(self, obj):
        """Sut/go'sht sotib bo'lmaydigan oxirgi kun (davolash tugamagan bo'lsa None)."""
        if obj.event_type != 'davolash' or not obj.withdrawal_days or not obj.end_date:
            return None
        return obj.end_date + timedelta(days=obj.withdrawal_days)

    def get_newborn_cards(self, obj):
        """Shu tug'ilish bilan birga ochilgan va hali faol buzoq kartochkalari soni."""
        return obj.newborns.filter(status='faol').count()

    def create(self, validated_data):
        validated_data.pop('calves', None)  # kartochkalarni view ochadi, AnimalEvent modeliga bu maydon yo'q
        return super().create(validated_data)

    def validate_animal_count(self, value):
        if value is not None and value < 1:
            raise serializers.ValidationError("Hayvonlar soni kamida 1 bo'lishi kerak")
        return value

    @staticmethod
    def _validate_calves(calves, event_type, count, group, mother, start):
        if event_type != 'tugilish':
            raise serializers.ValidationError({'calves': "Buzoq kartochkalari faqat tug'ilish uchun kiritiladi"})
        if len(calves) > count:
            raise serializers.ValidationError({'calves': (
                f"Kartochkalar soni ({len(calves)}) tug'ilgan hayvonlar sonidan ({count}) ko'p bo'lishi mumkin emas")})
        if start and start > timezone.localdate():
            raise serializers.ValidationError(
                {'start_date': "Kartochka ochish uchun tug'ilgan sana kelajakda bo'lishi mumkin emas"})
        if mother is not None and mother.sex != 'urgochi':
            raise serializers.ValidationError({'animal': "Ona urg'ochi bo'lishi kerak"})
        tags = [c['tag_number'] for c in calves]
        repeated = sorted({t for t in tags if tags.count(t) > 1})
        if repeated:
            raise serializers.ValidationError({'calves': f"Quloq raqami takrorlangan: {', '.join(repeated)}"})
        taken = sorted(Animal.objects.filter(farm_id=group.farm_id, tag_number__in=tags)
                       .values_list('tag_number', flat=True))
        if taken:
            raise serializers.ValidationError(
                {'calves': f"Bu quloq raqami fermada allaqachon bor: {', '.join(taken)}"})

    def validate(self, attrs):
        start = attrs.get('start_date', getattr(self.instance, 'start_date', None))
        end = attrs.get('end_date', getattr(self.instance, 'end_date', None))
        status = attrs.get('status', getattr(self.instance, 'status', None))

        # Voqea aniq hayvonga bog'langan bo'lsa, u shu guruhniki bo'lishi kerak
        animal = attrs.get('animal')
        if animal is not None:
            group_for_animal = attrs.get('animal_group', getattr(self.instance, 'animal_group', None))
            if group_for_animal and animal.group_id != group_for_animal.id:
                raise serializers.ValidationError({'animal': "Bu hayvon tanlangan guruhga tegishli emas"})

        # Dori va ushlab turish muddati faqat davolash uchun
        event_type_now = attrs.get('event_type', getattr(self.instance, 'event_type', None))
        medicine = attrs.get('medicine')
        group_now = attrs.get('animal_group', getattr(self.instance, 'animal_group', None))
        if event_type_now != 'davolash':
            attrs['medicine'] = None
            attrs['withdrawal_days'] = 0
        else:
            if medicine is not None:
                if group_now and medicine.farm_id != group_now.farm_id:
                    raise serializers.ValidationError({'medicine': "Bu dori boshqa fermaniki"})
                if medicine.item_type != 'dori':
                    raise serializers.ValidationError({'medicine': "Faqat ombordagi dori-darmonni tanlash mumkin"})
                if 'withdrawal_days' not in attrs:
                    attrs['withdrawal_days'] = medicine.withdrawal_days  # dorining odatdagi muddati

        if self.instance is None:
            event_type = attrs.get('event_type')
            count = attrs.get('animal_count')
            group = attrs.get('animal_group')
            if animal is not None and event_type == 'olim':
                # Bitta aniq hayvon o'ldi: soni har doim 1
                if animal.status != 'faol':
                    raise serializers.ValidationError({'animal': "Faqat faol hayvon uchun o'lim yozish mumkin"})
                if count not in (None, 1):
                    raise serializers.ValidationError({'animal_count': "Aniq bitta hayvon uchun soni 1 bo'lishi kerak"})
                attrs['animal_count'] = count = 1
            if event_type in COUNT_EVENT_TYPES:
                if not count:
                    raise serializers.ValidationError({'animal_count': "Nechta hayvon ekanini kiriting"})
                # O'lim va tug'ilish bir lahzalik hodisa: darhol yakunlangan hisoblanadi
                attrs['status'] = status = 'yakunlangan'
                attrs.setdefault('end_date', start)
                end = attrs['end_date']
            if count and event_type != 'tugilish' and group and count > group.count:
                raise serializers.ValidationError(
                    {'animal_count': f"Guruhda faqat {group.count} ta hayvon bor"})
            calves = attrs.get('calves')
            if calves:
                self._validate_calves(calves, event_type, count, group, animal, start)
        elif attrs.get('calves'):
            raise serializers.ValidationError(
                {'calves': "Buzoq kartochkalarini faqat yangi tug'ilish yozuvida kiritish mumkin"})

        # Yakunlangan ishga tugash sanasi avtomatik qo'yiladi
        if status == 'yakunlangan' and not end:
            end = timezone.localdate()
            attrs['end_date'] = end

        if start and end and end < start:
            raise serializers.ValidationError(
                {'end_date': "Tugash sanasi boshlanish sanasidan oldin bo'lishi mumkin emas"})
        return attrs


# Bug'ozlik muddati (kun). Hayvon turi nomida shu so'z bo'lsa, tug'ish sanasi o'zi hisoblanadi.
GESTATION_DAYS = (
    ('sigir', 283), ('qoramol', 283), ('buzoq', 283), ('mol', 283),
    ("qo'y", 150), ('echki', 150), ('ot', 340), ('biya', 340),
    ('tuya', 390), ("cho'chqa", 114),
)


def gestation_days(type_name):
    name = (type_name or '').lower()
    for ch in ('\u02bb', '\u2018', '\u2019', '`', '\u02bc'):
        name = name.replace(ch, "'")
    for word, days in GESTATION_DAYS:
        if word in name:
            return days
    return None


def months_between(born, today):
    months = (today.year - born.year) * 12 + today.month - born.month
    return months - 1 if today.day < born.day else months


# Hayvon davrlari: yoshi va tug'ish/bug'ozlik tarixidan avtomatik aniqlanadi (qo'lda o'zgartirilmaydi)
BREEDING_AGE_MONTHS = 12   # shu yoshdan keyin urug'lantirish/bug'ozlik yozish mumkin
ADULT_AGE_MONTHS = 24      # tug'magan bo'lsa ham shu yoshdan keyin "sigir" hisoblanadi
STAGE_LABELS = {
    'buzoq': 'Buzoq', 'gunajin': "G'unajin", 'sigir': 'Sigir', 'buqa': 'Buqa',
}


def animal_stage(animal, calved, today=None):
    """
    Urg'ochi: buzoq (12 oygacha) -> g'unajin (12-24 oy, hali tug'magan) -> sigir.
    Bug'ozlik yoki tug'ish yozilishi bilan hayvon darhol "sigir" davriga o'tadi.
    Erkak: buzoq (12 oygacha) -> buqa.
    """
    today = today or timezone.localdate()
    age = months_between(animal.birth_date, today) if animal.birth_date else None
    if animal.sex == 'erkak':
        return 'buzoq' if age is not None and age < BREEDING_AGE_MONTHS else 'buqa'
    if calved or animal.pregnant_since is not None:
        return 'sigir'
    if age is None or age >= ADULT_AGE_MONTHS:
        return 'sigir'
    return 'buzoq' if age < BREEDING_AGE_MONTHS else 'gunajin'


class AnimalSerializer(serializers.ModelSerializer):
    farm = serializers.IntegerField(source='group.farm_id', read_only=True)
    group_label = serializers.SerializerMethodField()
    sex_display = serializers.CharField(source='get_sex_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    mother_tag = serializers.CharField(source='mother.tag_number', read_only=True, default=None)
    # View querysetga annotate qilinadi (N+1 bo'lmasligi uchun); annotate bo'lmasa None
    last_weight = serializers.SerializerMethodField()
    last_weight_date = serializers.SerializerMethodField()
    last_calving_date = serializers.SerializerMethodField()
    is_pregnant = serializers.SerializerMethodField()
    days_to_calving = serializers.SerializerMethodField()
    stage = serializers.SerializerMethodField()
    stage_display = serializers.SerializerMethodField()
    withdrawal = serializers.SerializerMethodField()

    class Meta:
        model = Animal
        fields = ['id', 'farm', 'group', 'group_label', 'tag_number', 'name', 'sex', 'sex_display',
                  'stage', 'stage_display',
                  'birth_date', 'mother', 'mother_tag', 'status', 'status_display', 'notes',
                  'pregnant_since', 'due_date', 'is_pregnant', 'days_to_calving',
                  'withdrawal',
                  'last_weight', 'last_weight_date', 'last_calving_date', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']

    def get_withdrawal(self, obj):
        """Davolashdan keyingi ushlab turish: sut va go'shtni sotib bo'lmaydi (yo'q bo'lsa None)."""
        if obj.status != 'faol':
            return None
        cache = self.context.setdefault('_withdrawals', {})
        if obj.farm_id not in cache:
            cache[obj.farm_id] = withdrawal_map(obj.farm_id, timezone.localdate())
        row = cache[obj.farm_id].get(obj.pk)
        if row is None:
            return None
        return {'until': row['until'], 'ongoing': row['until'] is None,
                'days_left': row['days_left'], 'medicine': row['medicine']}

    def get_group_label(self, obj):
        group = obj.group
        return f"{group.animal_type.name} ({group.breed})" if group.breed else group.animal_type.name

    def get_is_pregnant(self, obj):
        return obj.pregnant_since is not None

    def get_stage(self, obj):
        calved = getattr(obj, 'last_calving_date', None) is not None
        if not calved and obj.sex == 'urgochi' and obj.pk:
            calved = obj.calves.exists()  # annotate bo'lmagan joyda (masalan yangi yaratilganda)
        return animal_stage(obj, calved)

    def get_stage_display(self, obj):
        return STAGE_LABELS[self.get_stage(obj)]

    def get_days_to_calving(self, obj):
        if obj.pregnant_since is None or obj.due_date is None:
            return None
        return (obj.due_date - timezone.localdate()).days

    def get_last_weight(self, obj):
        value = getattr(obj, 'last_weight', None)
        # SQLite subquery 450 qaytaradi, PostgreSQL 450.0: har doim bir xil (1 ta kasr raqami) ko'rinsin
        return None if value is None else str(Decimal(value).quantize(Decimal('0.1')))

    def get_last_weight_date(self, obj):
        return getattr(obj, 'last_weight_date', None)

    def get_last_calving_date(self, obj):
        return getattr(obj, 'last_calving_date', None)

    def validate_tag_number(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Quloq raqamini kiriting")
        return value

    def validate_birth_date(self, value):
        if value and value > timezone.localdate():
            raise serializers.ValidationError("Tug'ilgan sana kelajakda bo'lishi mumkin emas")
        return value

    def validate(self, attrs):
        instance = self.instance
        group = attrs.get('group', getattr(instance, 'group', None))
        # Tug'ilgan sana majburiy (yoshi bo'yicha sut/bug'ozlik bo'limlari ko'rsatiladi)
        if (instance is None and not attrs.get('birth_date')) or ('birth_date' in attrs and attrs['birth_date'] is None):
            raise serializers.ValidationError({'birth_date': "Tug'ilgan sanani kiriting"})
        self._validate_pregnancy(attrs, instance, group)
        if instance is not None and 'group' in attrs and attrs['group'].farm_id != instance.farm_id:
            raise serializers.ValidationError({'group': "Hayvonni boshqa fermaga ko'chirib bo'lmaydi"})

        tag = attrs.get('tag_number', getattr(instance, 'tag_number', None))
        if group is not None and tag:
            clash = Animal.objects.filter(farm_id=group.farm_id, tag_number=tag)
            if instance is not None:
                clash = clash.exclude(pk=instance.pk)
            if clash.exists():
                raise serializers.ValidationError({'tag_number': "Bu quloq raqami fermada allaqachon bor"})

        mother = attrs.get('mother')
        if mother is not None:
            if group is not None and mother.farm_id != group.farm_id:
                raise serializers.ValidationError({'mother': "Ona boshqa fermaga tegishli"})
            if mother.sex != 'urgochi':
                raise serializers.ValidationError({'mother': "Ona urg'ochi bo'lishi kerak"})
            if instance is not None and mother.pk == instance.pk:
                raise serializers.ValidationError({'mother': "Hayvon o'zining onasi bo'la olmaydi"})
        return attrs


    def _validate_pregnancy(self, attrs, instance, group):
        sex = attrs.get('sex', getattr(instance, 'sex', 'urgochi'))
        status = attrs.get('status', getattr(instance, 'status', 'faol'))
        since = attrs.get('pregnant_since', getattr(instance, 'pregnant_since', None))

        # Bug'ozlik tugadi: sana o'chsa, tug'ish sanasi ham o'chadi
        if 'pregnant_since' in attrs and attrs['pregnant_since'] is None:
            attrs['due_date'] = None
            return
        # Hayvon sotilsa/o'lsa yoki erkak qilib o'zgartirilsa, bug'ozlik o'zi tugaydi
        if since is not None and (status != 'faol' or sex != 'urgochi'):
            if attrs.get('pregnant_since') is not None:
                raise serializers.ValidationError({'pregnant_since': "Faqat faol urg'ochi hayvon bug'oz bo'la oladi"})
            attrs['pregnant_since'] = None
            attrs['due_date'] = None
            return
        if since is None:
            if attrs.get('due_date') is not None:
                raise serializers.ValidationError({'due_date': "Avval bug'ozlik boshlangan sanani kiriting"})
            return

        if 'pregnant_since' in attrs and since > timezone.localdate():
            raise serializers.ValidationError({'pregnant_since': "Sana kelajakda bo'lishi mumkin emas"})
        if 'pregnant_since' in attrs and 'due_date' not in attrs:
            days = gestation_days(group.animal_type.name) if group is not None else None
            attrs['due_date'] = since + timedelta(days=days) if days else None
        due = attrs.get('due_date', getattr(instance, 'due_date', None))
        if due is not None and due < since:
            raise serializers.ValidationError({'due_date': "Tug'ish sanasi bug'ozlik boshlangan sanadan oldin bo'lishi mumkin emas"})


class _AnimalRecordSerializer(serializers.ModelSerializer):
    """Vazn va sut yozuvlari uchun umumiy qismlar."""
    animal_tag = serializers.CharField(source='animal.tag_number', read_only=True)
    farm = serializers.IntegerField(source='animal.farm_id', read_only=True)
    recorded_by_name = serializers.SerializerMethodField()

    def get_recorded_by_name(self, obj):
        user = obj.recorded_by
        if not user:
            return None
        return user.get_full_name() or user.username

    def _check_common(self, attrs):
        animal = attrs.get('animal', getattr(self.instance, 'animal', None))
        date = attrs.get('date', getattr(self.instance, 'date', None))
        if self.instance is not None and 'animal' in attrs and attrs['animal'].pk != self.instance.animal_id:
            raise serializers.ValidationError({'animal': "Yozuvni boshqa hayvonga ko'chirib bo'lmaydi"})
        if self.instance is None and animal is not None and animal.status != 'faol':
            raise serializers.ValidationError({'animal': "Faol bo'lmagan hayvonga yozuv qo'shib bo'lmaydi"})
        if date and date > timezone.localdate():
            raise serializers.ValidationError({'date': "Sana kelajakda bo'lishi mumkin emas"})
        if date and animal is not None and animal.birth_date and date < animal.birth_date:
            raise serializers.ValidationError({'date': "Sana hayvon tug'ilgan sanasidan oldin bo'lishi mumkin emas"})
        return animal, date


class WeightRecordSerializer(_AnimalRecordSerializer):
    class Meta:
        model = WeightRecord
        fields = ['id', 'farm', 'animal', 'animal_tag', 'date', 'weight_kg',
                  'recorded_by', 'recorded_by_name', 'created_at']
        read_only_fields = ['recorded_by', 'created_at']
        validators = []  # takrorlanishni validate() da tekshiramiz (aniqroq xabar bilan)

    def validate_weight_kg(self, value):
        if value <= 0 or value > 3000:
            raise serializers.ValidationError("Vazn 0 dan katta va 3000 kg dan kichik bo'lishi kerak")
        return value

    def validate(self, attrs):
        animal, date = self._check_common(attrs)
        if animal is not None and date:
            clash = WeightRecord.objects.filter(animal=animal, date=date)
            if self.instance is not None:
                clash = clash.exclude(pk=self.instance.pk)
            if clash.exists():
                raise serializers.ValidationError({'date': "Bu sana uchun vazn allaqachon yozilgan"})
        return attrs


class MilkRecordSerializer(_AnimalRecordSerializer):
    session_display = serializers.CharField(source='get_session_display', read_only=True)

    class Meta:
        model = MilkRecord
        fields = ['id', 'farm', 'animal', 'animal_tag', 'date', 'session', 'session_display', 'liters',
                  'recorded_by', 'recorded_by_name', 'created_at']
        read_only_fields = ['recorded_by', 'created_at']
        validators = []  # takrorlanishni validate() da tekshiramiz (aniqroq xabar bilan)

    def validate_liters(self, value):
        if value <= 0 or value > 100:
            raise serializers.ValidationError("Sut miqdori 0 dan katta va 100 litrdan kichik bo'lishi kerak")
        return value

    def validate(self, attrs):
        animal, date = self._check_common(attrs)
        if self.instance is None and animal is not None and animal.sex != 'urgochi':
            raise serializers.ValidationError({'animal': "Sut faqat urg'ochi hayvon uchun yoziladi"})
        session = attrs.get('session', getattr(self.instance, 'session', 'kun'))
        if animal is not None and date:
            clash = MilkRecord.objects.filter(animal=animal, date=date, session=session)
            if self.instance is not None:
                clash = clash.exclude(pk=self.instance.pk)
            if clash.exists():
                raise serializers.ValidationError({'session': "Bu sana va vaqt uchun sut allaqachon yozilgan"})

            # "Butun kun" bilan ertalab/kechqurun bir kunda aralashmaydi: kun jami yozuvlar yig'indisi,
            # aralashsa o'sha sut ikki marta hisoblanib qoladi.
            others = MilkRecord.objects.filter(animal=animal, date=date)
            if self.instance is not None:
                others = others.exclude(pk=self.instance.pk)
            existing = set(others.values_list('session', flat=True))
            if session == 'kun' and existing & {'ertalab', 'kechqurun'}:
                raise serializers.ValidationError({
                    'session': "Bu kun uchun ertalab/kechqurungi sut yozilgan. "
                               "Butun kun uchun alohida yozish kerak emas: kun jami avtomatik hisoblanadi."
                })
            if session in ('ertalab', 'kechqurun') and 'kun' in existing:
                raise serializers.ValidationError({
                    'session': "Bu kun uchun butun kunlik sut yozilgan. "
                               "Ertalab/kechqurunni alohida yozish uchun avval butun kunlik yozuvni o'chiring."
                })
        return attrs


class MilkSaleSerializer(serializers.ModelSerializer):
    recorded_by_name = serializers.SerializerMethodField()
    on_credit = serializers.SerializerMethodField()
    party_name = serializers.SerializerMethodField()
    debt_remaining = serializers.SerializerMethodField()

    class Meta:
        model = MilkSale
        fields = ['id', 'farm', 'date', 'liters', 'price_per_liter', 'amount', 'note',
                  'on_credit', 'party_name', 'debt_remaining',
                  'recorded_by', 'recorded_by_name', 'created_at']
        read_only_fields = ['amount', 'recorded_by', 'created_at']

    def get_on_credit(self, obj):
        return obj.debt_id is not None

    def get_party_name(self, obj):
        return obj.debt.party.name if obj.debt_id else None

    def get_debt_remaining(self, obj):
        if not obj.debt_id:
            return None
        paid = sum((p.amount for p in obj.debt.payments.all()), Decimal('0'))
        return str(obj.debt.amount - paid)

    def get_recorded_by_name(self, obj):
        user = obj.recorded_by
        return (user.get_full_name() or user.username) if user else None

    def validate_liters(self, value):
        if value <= 0:
            raise serializers.ValidationError("Litr 0 dan katta bo'lishi kerak")
        return value

    def validate_price_per_liter(self, value):
        if value <= 0:
            raise serializers.ValidationError("Narx 0 dan katta bo'lishi kerak")
        return value

    def validate_date(self, value):
        if value > timezone.localdate():
            raise serializers.ValidationError("Sana kelajakda bo'lishi mumkin emas")
        return value
