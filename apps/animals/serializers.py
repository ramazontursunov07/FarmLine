from django.utils import timezone
from rest_framework import serializers

from .models import COUNT_EVENT_TYPES, Animal, AnimalType, AnimalGroup, AnimalEvent, MilkRecord, WeightRecord


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

    class Meta:
        model = AnimalEvent
        fields = ['id', 'farm', 'animal_group', 'animal_group_label', 'animal_group_count',
                  'animal', 'animal_tag',
                  'event_type', 'event_type_display', 'animal_count', 'title', 'description',
                  'status', 'status_display', 'start_date', 'end_date',
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

    def validate_animal_count(self, value):
        if value is not None and value < 1:
            raise serializers.ValidationError("Hayvonlar soni kamida 1 bo'lishi kerak")
        return value

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

        # Yakunlangan ishga tugash sanasi avtomatik qo'yiladi
        if status == 'yakunlangan' and not end:
            end = timezone.localdate()
            attrs['end_date'] = end

        if start and end and end < start:
            raise serializers.ValidationError(
                {'end_date': "Tugash sanasi boshlanish sanasidan oldin bo'lishi mumkin emas"})
        return attrs


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

    class Meta:
        model = Animal
        fields = ['id', 'farm', 'group', 'group_label', 'tag_number', 'name', 'sex', 'sex_display',
                  'birth_date', 'mother', 'mother_tag', 'status', 'status_display', 'notes',
                  'last_weight', 'last_weight_date', 'last_calving_date', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']

    def get_group_label(self, obj):
        group = obj.group
        return f"{group.animal_type.name} ({group.breed})" if group.breed else group.animal_type.name

    def get_last_weight(self, obj):
        value = getattr(obj, 'last_weight', None)
        return None if value is None else str(value)

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
        return attrs
