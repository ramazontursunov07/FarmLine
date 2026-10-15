from datetime import timedelta
from decimal import Decimal

from django.utils import timezone
from rest_framework.test import APITestCase

from apps.animals.models import Animal, AnimalEvent, AnimalGroup, AnimalType, MilkRecord, WeightRecord
from apps.farms.models import Farm, Worker
from apps.users.models import User

CARDS = '/api/animals-card/'
WEIGHTS = '/api/animals-weight/'
MILK = '/api/animals-milk/'
EVENTS = '/api/animals-event/'
GROUPS = '/api/animals-group/'


def rows(response):
    """Ro'yxat javobi (pagination yo'q bo'lsa list, bo'lsa results ichida)."""
    data = response.json()
    return data['results'] if isinstance(data, dict) else data


def make_user(username, role='fermer'):
    return User.objects.create_user(username=username, password='Kuchli-Parol-2026', role=role)


class AnimalCardBase(APITestCase):
    def setUp(self):
        self.owner = make_user('egasi')
        self.farm = Farm.objects.create(owner=self.owner, name='Baraka', location='Qarshi', farm_type='aralash')
        self.worker = make_user('ishchi', 'ishchi')
        Worker.objects.create(user=self.worker, farm=self.farm)
        self.type = AnimalType.objects.create(name='Qoramol')
        self.group = AnimalGroup.objects.create(farm=self.farm, animal_type=self.type, breed='Golshteyn', count=3)
        self.today = timezone.localdate()
        self.client.force_authenticate(self.owner)

    def new_card(self, tag='14', **extra):
        data = {'group': self.group.pk, 'tag_number': tag, 'name': 'Mushuk', 'sex': 'urgochi'}
        data.update(extra)
        return self.client.post(CARDS, data, format='json')

    def make_animal(self, tag='14', **extra):
        data = dict(farm=self.farm, group=self.group, tag_number=tag)
        data.update(extra)
        return Animal.objects.create(**data)


class AnimalCardCrudTests(AnimalCardBase):
    def test_owner_creates_card(self):
        r = self.new_card()
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()['farm'], self.farm.pk)
        self.assertEqual(r.json()['group_label'], 'Qoramol (Golshteyn)')
        self.assertEqual(Animal.objects.get().farm_id, self.farm.pk)

    def test_worker_cannot_create_card(self):
        self.client.force_authenticate(self.worker)
        self.assertEqual(self.new_card().status_code, 403)

    def test_worker_can_view_cards(self):
        self.make_animal()
        self.client.force_authenticate(self.worker)
        r = self.client.get(CARDS, {'farm': self.farm.pk})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(rows(r)), 1)

    def test_stranger_sees_nothing(self):
        animal = self.make_animal()
        self.client.force_authenticate(make_user('begona'))
        r = self.client.get(CARDS)
        self.assertEqual(len(rows(r)), 0)
        self.assertEqual(self.client.get(f'{CARDS}{animal.pk}/').status_code, 404)
        self.assertEqual(self.client.get(f'{CARDS}{animal.pk}/card/').status_code, 404)

    def test_duplicate_tag_in_farm_rejected(self):
        self.assertEqual(self.new_card('14').status_code, 201)
        r = self.new_card('14')
        self.assertEqual(r.status_code, 400)
        self.assertIn('tag_number', r.json())

    def test_cards_cannot_exceed_group_count(self):
        self.group.count = 2
        self.group.save()
        self.assertEqual(self.new_card('1').status_code, 201)
        self.assertEqual(self.new_card('2').status_code, 201)
        r = self.new_card('3')
        self.assertEqual(r.status_code, 400)
        self.assertIn('group', r.json())

    def test_mother_must_be_female_and_same_farm(self):
        bull = self.make_animal('7', sex='erkak')
        self.assertEqual(self.new_card('8', mother=bull.pk).status_code, 400)
        other_farm = Farm.objects.create(owner=self.owner, name='Boshqa', location='X', farm_type='aralash')
        other_group = AnimalGroup.objects.create(farm=other_farm, animal_type=self.type, count=1)
        foreign = Animal.objects.create(farm=other_farm, group=other_group, tag_number='9')
        self.assertEqual(self.new_card('10', mother=foreign.pk).status_code, 400)
        cow = self.make_animal('11')
        self.assertEqual(self.new_card('12', mother=cow.pk).status_code, 201)

    def test_future_birth_date_rejected(self):
        r = self.new_card(birth_date=str(self.today + timedelta(days=1)))
        self.assertEqual(r.status_code, 400)

    def test_cannot_move_card_to_other_farm(self):
        animal = self.make_animal()
        other_farm = Farm.objects.create(owner=self.owner, name='Boshqa', location='X', farm_type='aralash')
        other_group = AnimalGroup.objects.create(farm=other_farm, animal_type=self.type, count=5)
        r = self.client.patch(f'{CARDS}{animal.pk}/', {'group': other_group.pk}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_manual_status_olgan_rejected(self):
        animal = self.make_animal()
        r = self.client.patch(f'{CARDS}{animal.pk}/', {'status': 'olgan'}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_group_count_cannot_drop_below_cards(self):
        self.make_animal('1')
        self.make_animal('2')
        r = self.client.patch(f'{GROUPS}{self.group.pk}/', {'count': 1}, format='json')
        self.assertEqual(r.status_code, 400)
        r = self.client.patch(f'{GROUPS}{self.group.pk}/', {'count': 2}, format='json')
        self.assertEqual(r.status_code, 200)

    def test_idempotency_key_prevents_duplicate_card(self):
        headers = {'HTTP_IDEMPOTENCY_KEY': 'karta-test-12345'}
        r1 = self.client.post(CARDS, {'group': self.group.pk, 'tag_number': '5'}, format='json', **headers)
        r2 = self.client.post(CARDS, {'group': self.group.pk, 'tag_number': '5'}, format='json', **headers)
        self.assertEqual((r1.status_code, r2.status_code), (201, 201))
        self.assertEqual(Animal.objects.count(), 1)


class WeightMilkTests(AnimalCardBase):
    def setUp(self):
        super().setUp()
        self.cow = self.make_animal('14')

    def weight(self, date=None, kg='450.5', animal=None):
        return self.client.post(WEIGHTS, {'animal': (animal or self.cow).pk,
                                          'date': str(date or self.today), 'weight_kg': kg}, format='json')

    def milk(self, date=None, liters='18.5', session='kun', animal=None):
        return self.client.post(MILK, {'animal': (animal or self.cow).pk, 'date': str(date or self.today),
                                       'liters': liters, 'session': session}, format='json')

    def test_worker_can_add_weight_and_milk(self):
        self.client.force_authenticate(self.worker)
        r = self.weight()
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(WeightRecord.objects.get().recorded_by, self.worker)
        self.assertEqual(self.milk().status_code, 201)
        self.assertEqual(MilkRecord.objects.get().recorded_by, self.worker)

    def test_stranger_cannot_add_records(self):
        self.client.force_authenticate(make_user('begona'))
        self.assertEqual(self.weight().status_code, 403)
        self.assertEqual(self.milk().status_code, 403)

    def test_weight_validation(self):
        self.assertEqual(self.weight(kg='0').status_code, 400)
        self.assertEqual(self.weight(kg='5000').status_code, 400)
        self.assertEqual(self.weight(date=self.today + timedelta(days=1)).status_code, 400)
        self.assertEqual(self.weight().status_code, 201)
        self.assertEqual(self.weight(kg='460').status_code, 400)  # shu kunga ikkinchi vazn

    def test_weight_before_birth_rejected(self):
        calf = self.make_animal('15', birth_date=self.today - timedelta(days=10))
        r = self.weight(date=self.today - timedelta(days=20), animal=calf)
        self.assertEqual(r.status_code, 400)

    def test_milk_validation(self):
        self.assertEqual(self.milk(liters='0').status_code, 400)
        self.assertEqual(self.milk(liters='500').status_code, 400)
        self.assertEqual(self.milk(session='ertalab').status_code, 201)
        self.assertEqual(self.milk(session='ertalab').status_code, 400)  # takror
        self.assertEqual(self.milk(session='kechqurun').status_code, 201)

    def test_milk_only_for_female(self):
        bull = self.make_animal('77', sex='erkak')
        self.assertEqual(self.milk(animal=bull).status_code, 400)

    def test_records_for_inactive_animal_rejected(self):
        sold = self.make_animal('88', status='sotilgan')
        self.assertEqual(self.weight(animal=sold).status_code, 400)

    def test_only_owner_or_author_can_delete(self):
        self.client.force_authenticate(self.worker)
        rec_id = self.weight().json()['id']
        other = make_user('ishchi2', 'ishchi')
        Worker.objects.create(user=other, farm=self.farm)
        self.client.force_authenticate(other)
        self.assertEqual(self.client.delete(f'{WEIGHTS}{rec_id}/').status_code, 403)
        self.client.force_authenticate(self.worker)
        self.assertEqual(self.client.delete(f'{WEIGHTS}{rec_id}/').status_code, 204)

    def test_date_filter(self):
        self.weight(date=self.today - timedelta(days=5), kg='440')
        self.weight(date=self.today, kg='450')
        r = self.client.get(WEIGHTS, {'animal': self.cow.pk, 'date_from': str(self.today - timedelta(days=1))})
        self.assertEqual(len(rows(r)), 1)
        self.assertEqual(self.client.get(WEIGHTS, {'date_from': 'xato'}).status_code, 400)


class AnimalCardEndpointTests(AnimalCardBase):
    def test_card_summary(self):
        cow = self.make_animal('14')
        d = self.today
        for days_ago, kg in ((10, '440.0'), (0, '450.0')):
            WeightRecord.objects.create(animal=cow, date=d - timedelta(days=days_ago), weight_kg=Decimal(kg))
        for days_ago, liters in ((0, '10.0'), (1, '20.0')):
            MilkRecord.objects.create(animal=cow, date=d - timedelta(days=days_ago), liters=Decimal(liters))
        MilkRecord.objects.create(animal=cow, date=d, session='ertalab', liters=Decimal('5.0'))  # bir kunda 2 yozuv
        MilkRecord.objects.create(animal=cow, date=d - timedelta(days=60), liters=Decimal('99.0'))  # oynadan tashqari
        AnimalEvent.objects.create(animal_group=self.group, animal=cow, event_type='tugilish', title='Buzoq',
                                   start_date=d - timedelta(days=100), end_date=d - timedelta(days=100),
                                   animal_count=1, status='yakunlangan')
        calf = self.make_animal('15', mother=cow)

        r = self.client.get(f'{CARDS}{cow.pk}/card/')
        self.assertEqual(r.status_code, 200, r.content)
        body = r.json()
        self.assertEqual(body['animal']['tag_number'], '14')
        self.assertEqual(body['animal']['last_weight'], '450.0')
        self.assertEqual(body['last_calving_date'], str(d - timedelta(days=100)))
        ws = body['weight_summary']
        self.assertEqual((ws['last'], ws['previous'], ws['change_kg'], ws['daily_gain_g']),
                         ('450.0', '440.0', '10.0', 1000))
        self.assertEqual([w['weight_kg'] for w in body['weights']], ['440.0', '450.0'])  # eskidan yangiga
        milk = body['milk']
        self.assertEqual((milk['days_recorded'], milk['total_liters'], milk['daily_average']), (2, '35.0', '17.5'))
        self.assertEqual(milk['last_day_liters'], '15.0')
        self.assertEqual([c['id'] for c in body['calves']], [calf.pk])
        self.assertEqual(len(body['events']), 1)

    def test_empty_card(self):
        cow = self.make_animal('14')
        body = self.client.get(f'{CARDS}{cow.pk}/card/').json()
        self.assertIsNone(body['weight_summary']['last'])
        self.assertIsNone(body['milk']['daily_average'])
        self.assertEqual((body['weights'], body['events'], body['calves']), ([], [], []))

    def test_list_includes_last_weight_and_calving(self):
        cow = self.make_animal('14', name='Mushuk')
        WeightRecord.objects.create(animal=cow, date=self.today, weight_kg=Decimal('455.0'))
        r = self.client.get(CARDS, {'farm': self.farm.pk, 'search': 'mush'})
        found = rows(r)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]['last_weight'], '455.0')
        self.assertIsNone(found[0]['last_calving_date'])
        self.assertEqual(rows(self.client.get(CARDS, {'search': 'yoq-bunaqa'})), [])


class DeathEventTests(AnimalCardBase):
    def death(self, animal=None, count=None, group=None):
        data = {'animal_group': (group or self.group).pk, 'event_type': 'olim', 'title': "O'ldi",
                'start_date': str(self.today)}
        if animal:
            data['animal'] = animal.pk
        if count is not None:
            data['animal_count'] = count
        return self.client.post(EVENTS, data, format='json')

    def test_death_of_specific_animal(self):
        cow = self.make_animal('14')
        r = self.death(animal=cow)
        self.assertEqual(r.status_code, 201, r.content)
        cow.refresh_from_db()
        self.group.refresh_from_db()
        self.assertEqual(cow.status, 'olgan')
        self.assertEqual(self.group.count, 2)
        self.assertEqual(r.json()['animal_count'], 1)

    def test_death_with_wrong_count_for_animal_rejected(self):
        cow = self.make_animal('14')
        self.assertEqual(self.death(animal=cow, count=2).status_code, 400)

    def test_animal_must_belong_to_event_group(self):
        other_group = AnimalGroup.objects.create(farm=self.farm, animal_type=self.type, count=2)
        cow = self.make_animal('14')
        r = self.death(animal=cow, group=other_group)
        self.assertEqual(r.status_code, 400)
        self.assertIn('animal', r.json())

    def test_cannot_kill_dead_animal_twice(self):
        cow = self.make_animal('14')
        self.assertEqual(self.death(animal=cow).status_code, 201)
        self.assertEqual(self.death(animal=cow).status_code, 400)

    def test_unnamed_death_blocked_when_cards_would_exceed_count(self):
        self.group.count = 3
        self.group.save()
        for tag in ('1', '2', '3'):
            self.make_animal(tag)
        r = self.death(count=1)  # 2 ta qoladi, lekin 3 ta faol kartochka bor
        self.assertEqual(r.status_code, 400)
        self.group.refresh_from_db()
        self.assertEqual(self.group.count, 3)  # rollback

    def test_unnamed_death_allowed_when_cards_fit(self):
        self.make_animal('1')
        self.assertEqual(self.death(count=1).status_code, 201)
        self.group.refresh_from_db()
        self.assertEqual(self.group.count, 2)

    def test_delete_death_restores_animal_and_count(self):
        cow = self.make_animal('14')
        event_id = self.death(animal=cow).json()['id']
        self.assertEqual(self.client.delete(f'{EVENTS}{event_id}/').status_code, 204)
        cow.refresh_from_db()
        self.group.refresh_from_db()
        self.assertEqual((cow.status, self.group.count), ('faol', 3))

    def test_cannot_change_animal_on_death_event(self):
        cow = self.make_animal('14')
        other = self.make_animal('15')
        event_id = self.death(animal=cow).json()['id']
        r = self.client.patch(f'{EVENTS}{event_id}/', {'animal': other.pk}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_calving_event_attached_to_mother(self):
        cow = self.make_animal('14')
        r = self.client.post(EVENTS, {'animal_group': self.group.pk, 'animal': cow.pk, 'event_type': 'tugilish',
                                      'title': 'Buzoq tug\'ildi', 'animal_count': 1,
                                      'start_date': str(self.today)}, format='json')
        self.assertEqual(r.status_code, 201, r.content)
        self.group.refresh_from_db()
        self.assertEqual(self.group.count, 4)
        row = self.client.get(f'{CARDS}{cow.pk}/').json()
        self.assertEqual(row['last_calving_date'], str(self.today))
        self.assertEqual(len(rows(self.client.get(EVENTS, {'animal': cow.pk}))), 1)
