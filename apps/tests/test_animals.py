from datetime import timedelta
from unittest.mock import patch
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
        data = {'group': self.group.pk, 'tag_number': tag, 'name': 'Mushuk', 'sex': 'urgochi',
                'birth_date': str(self.today - timedelta(days=1000))}
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

    def test_deleting_active_card_reduces_group_count(self):
        cow = self.make_animal('14')
        self.assertEqual(self.client.delete(f'{CARDS}{cow.pk}/').status_code, 204)
        self.group.refresh_from_db()
        self.assertEqual(self.group.count, 2)
        self.assertFalse(Animal.objects.filter(pk=cow.pk).exists())

    def test_deleting_sold_card_keeps_group_count(self):
        sold = self.make_animal('15', status='sotilgan')
        self.assertEqual(self.client.delete(f'{CARDS}{sold.pk}/').status_code, 204)
        self.group.refresh_from_db()
        self.assertEqual(self.group.count, 3)

    def test_deleting_card_does_not_go_below_zero(self):
        self.group.count = 0
        self.group.status = 'faol'
        self.group.save()
        cow = self.make_animal('16', status='faol')
        self.assertEqual(self.client.delete(f'{CARDS}{cow.pk}/').status_code, 204)
        self.group.refresh_from_db()
        self.assertEqual(self.group.count, 0)

    def test_worker_cannot_delete_card_or_change_count(self):
        cow = self.make_animal('17')
        self.client.force_authenticate(self.worker)
        self.assertEqual(self.client.delete(f'{CARDS}{cow.pk}/').status_code, 403)
        self.group.refresh_from_db()
        self.assertEqual(self.group.count, 3)

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

    def test_birth_date_is_required(self):
        r = self.client.post(CARDS, {'group': self.group.pk, 'tag_number': '40', 'sex': 'urgochi'}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertIn('birth_date', r.json())
        cow = self.make_animal('41', birth_date=self.today - timedelta(days=900))
        r = self.client.patch(f'{CARDS}{cow.pk}/', {'birth_date': None}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_duplicate_tag_in_farm_rejected(self):
        self.assertEqual(self.new_card('14').status_code, 201)
        r = self.new_card('14')
        self.assertEqual(r.status_code, 400)
        self.assertIn('tag_number', r.json())

    def test_new_card_raises_group_count(self):
        self.group.count = 2
        self.group.save()
        for tag in ('1', '2', '3'):
            self.assertEqual(self.new_card(tag).status_code, 201)
        self.group.refresh_from_db()
        self.assertEqual(self.group.count, 3)

    def test_empty_group_fills_up_with_cards(self):
        self.group.count = 0
        self.group.save()
        self.assertEqual(self.new_card('1').status_code, 201)
        self.group.refresh_from_db()
        self.assertEqual(self.group.count, 1)

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
        r1 = self.client.post(CARDS, {'group': self.group.pk, 'tag_number': '5', 'birth_date': '2023-01-01'},
                              format='json', **headers)
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

    def test_whole_day_milk_not_allowed_after_morning_and_evening(self):
        self.assertEqual(self.milk(session='ertalab').status_code, 201)
        self.assertEqual(self.milk(session='kechqurun').status_code, 201)
        r = self.milk(session='kun')
        self.assertEqual(r.status_code, 400)
        self.assertIn('session', r.json())
        self.assertEqual(MilkRecord.objects.count(), 2)

    def test_whole_day_milk_not_allowed_after_only_morning(self):
        self.assertEqual(self.milk(session='ertalab').status_code, 201)
        self.assertEqual(self.milk(session='kun').status_code, 400)

    def test_morning_not_allowed_after_whole_day(self):
        self.assertEqual(self.milk(session='kun').status_code, 201)
        self.assertEqual(self.milk(session='ertalab').status_code, 400)
        self.assertEqual(self.milk(session='kechqurun').status_code, 400)

    def test_whole_day_milk_other_day_and_other_cow_ok(self):
        self.assertEqual(self.milk(session='ertalab').status_code, 201)
        self.assertEqual(self.milk(date=self.today - timedelta(days=1), session='kun').status_code, 201)

    # --- Sut hisoboti: har bir sigir va jami, o'tgan oy bilan
    def _milk_rows(self):
        first = self.today.replace(day=1)
        prev = first - timedelta(days=1)
        cow2 = self.make_animal('15', name='Qora')
        MilkRecord.objects.create(animal=self.cow, date=first, session='ertalab', liters=Decimal('10.0'))
        MilkRecord.objects.create(animal=self.cow, date=first, session='kechqurun', liters=Decimal('8.0'))
        MilkRecord.objects.create(animal=cow2, date=first, session='kun', liters=Decimal('5.5'))
        MilkRecord.objects.create(animal=self.cow, date=prev, session='kun', liters=Decimal('20.0'))
        MilkRecord.objects.create(animal=cow2, date=prev, session='kun', liters=Decimal('7.0'))
        return cow2

    def test_milk_summary_per_cow_and_total(self):
        cow2 = self._milk_rows()
        r = self.client.get(MILK + 'summary/', {'farm': self.farm.pk})
        self.assertEqual(r.status_code, 200, r.content)
        data = r.json()
        self.assertEqual(data['month'], f"{self.today:%Y-%m}")
        self.assertEqual(Decimal(data['total']), Decimal('23.5'))
        self.assertEqual(Decimal(data['previous_total']), Decimal('27.0'))
        self.assertEqual(Decimal(data['change']), Decimal('-3.5'))
        self.assertEqual(data['animals_count'], 2)
        # eng ko'p sut bergan birinchi
        self.assertEqual([a['animal'] for a in data['animals']], [self.cow.pk, cow2.pk])
        first = data['animals'][0]
        self.assertEqual(Decimal(first['liters']), Decimal('18.0'))
        self.assertEqual(Decimal(first['previous_liters']), Decimal('20.0'))
        self.assertEqual(first['days'], 1)
        self.assertEqual(Decimal(first['daily_average']), Decimal('18.0'))

    def test_milk_summary_explicit_month(self):
        self._milk_rows()
        prev = self.today.replace(day=1) - timedelta(days=1)
        r = self.client.get(MILK + 'summary/', {'farm': self.farm.pk, 'month': f"{prev:%Y-%m}"})
        self.assertEqual(Decimal(r.json()['total']), Decimal('27.0'))

    def test_milk_summary_not_doubled_with_many_workers(self):
        self._milk_rows()
        other = make_user('ishchi2', 'ishchi')
        Worker.objects.create(user=other, farm=self.farm)  # ikkinchi ishchi: yozuvlar ikki marta sanalmasin
        r = self.client.get(MILK + 'summary/', {'farm': self.farm.pk})
        self.assertEqual(Decimal(r.json()['total']), Decimal('23.5'))

    def test_milk_summary_worker_can_view_but_stranger_sees_nothing(self):
        self._milk_rows()
        self.client.force_authenticate(self.worker)
        self.assertEqual(Decimal(self.client.get(MILK + 'summary/').json()['total']), Decimal('23.5'))
        self.client.force_authenticate(make_user('begona'))
        r = self.client.get(MILK + 'summary/', {'farm': self.farm.pk})
        self.assertEqual((Decimal(r.json()['total']), r.json()['animals']), (Decimal('0.0'), []))

    def test_milk_summary_bad_month(self):
        for bad in ('2026-13', 'abc', '2026'):
            self.assertEqual(self.client.get(MILK + 'summary/', {'month': bad}).status_code, 400, bad)

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


class CalvingWithCardsTests(AnimalCardBase):
    """Tug'ilish yozuvi bilan birga buzoq kartochkalarini ochish."""

    def calving(self, calves=None, count=2, **extra):
        data = {'animal_group': self.group.pk, 'event_type': 'tugilish', 'title': "Buzoqlar tug'ildi",
                'animal_count': count, 'start_date': str(self.today)}
        if calves is not None:
            data['calves'] = calves
        data.update(extra)
        return self.client.post(EVENTS, data, format='json')

    def assert_nothing_saved(self):
        """Xato bo'lganda na yozuv, na kartochka, na guruh soni o'zgargan bo'lishi kerak."""
        self.group.refresh_from_db()
        self.assertEqual(self.group.count, 3)
        self.assertEqual(AnimalEvent.objects.count(), 0)
        self.assertEqual(Animal.objects.count(), 0)

    def test_birth_opens_cards_and_updates_group(self):
        r = self.calving([{'tag_number': '21', 'name': 'Qora'}, {'tag_number': '22', 'sex': 'erkak'}])
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(sorted(c['tag_number'] for c in r.json()['calves_created']), ['21', '22'])
        self.assertNotIn('calves', r.json())  # faqat yozish uchun
        self.group.refresh_from_db()
        self.assertEqual(self.group.count, 5)
        cards = {a.tag_number: a for a in Animal.objects.all()}
        self.assertEqual(cards['21'].sex, 'urgochi')  # sex berilmasa
        self.assertEqual(cards['22'].sex, 'erkak')
        for card in cards.values():
            self.assertEqual((card.farm_id, card.group_id, card.status), (self.farm.pk, self.group.pk, 'faol'))
            self.assertEqual(card.birth_date, self.today)  # buzoq tug'ilgan sana = yozuv sanasi

    def test_cards_linked_to_mother(self):
        cow = self.make_animal('14')
        r = self.calving([{'tag_number': '21'}], count=1, animal=cow.pk)
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(Animal.objects.get(tag_number='21').mother_id, cow.pk)
        self.assertEqual(self.client.get(f'{CARDS}{cow.pk}/card/').json()['calves'][0]['tag_number'], '21')

    def test_fewer_cards_than_calves_allowed(self):
        r = self.calving([{'tag_number': '21'}], count=2)
        self.assertEqual(r.status_code, 201, r.content)
        self.group.refresh_from_db()
        self.assertEqual((self.group.count, Animal.objects.count()), (5, 1))

    def test_without_calves_behaves_as_before(self):
        r = self.calving(None, count=2)
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()['calves_created'], [])
        self.group.refresh_from_db()
        self.assertEqual((self.group.count, Animal.objects.count()), (5, 0))

    def test_more_cards_than_calves_rejected(self):
        r = self.calving([{'tag_number': '21'}, {'tag_number': '22'}], count=1)
        self.assertEqual(r.status_code, 400)
        self.assert_nothing_saved()

    def test_duplicate_tags_in_request_rejected(self):
        r = self.calving([{'tag_number': '21'}, {'tag_number': '21'}])
        self.assertEqual(r.status_code, 400)
        self.assertIn('takrorlangan', r.json()['calves'][0])
        self.assert_nothing_saved()

    def test_existing_tag_rejected_and_nothing_saved(self):
        self.make_animal('21')
        r = self.calving([{'tag_number': '22'}, {'tag_number': '21'}])
        self.assertEqual(r.status_code, 400)
        self.assertIn('allaqachon', r.json()['calves'][0])
        self.group.refresh_from_db()
        self.assertEqual((self.group.count, AnimalEvent.objects.count(), Animal.objects.count()), (3, 0, 1))

    def test_blank_tag_rejected(self):
        r = self.calving([{'tag_number': '   '}], count=1)
        self.assertEqual(r.status_code, 400)
        self.assert_nothing_saved()

    def test_cards_only_for_birth(self):
        r = self.client.post(EVENTS, {'animal_group': self.group.pk, 'event_type': 'kasallik', 'title': 'Shamollash',
                                      'start_date': str(self.today), 'calves': [{'tag_number': '21'}]}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assert_nothing_saved()

    def test_cards_cannot_be_added_on_update(self):
        event_id = self.calving(None, count=1).json()['id']
        r = self.client.patch(f'{EVENTS}{event_id}/', {'calves': [{'tag_number': '21'}]}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertEqual(Animal.objects.count(), 0)

    def test_future_birth_date_rejected(self):
        r = self.calving([{'tag_number': '21'}], count=1, start_date=str(self.today + timedelta(days=2)))
        self.assertEqual(r.status_code, 400)
        self.assert_nothing_saved()

    def test_male_mother_rejected(self):
        bull = self.make_animal('7', sex='erkak')
        r = self.calving([{'tag_number': '21'}], count=1, animal=bull.pk)
        self.assertEqual(r.status_code, 400)
        self.group.refresh_from_db()
        # Faqat testning o'zi yaratgan buqa qolgan: na yozuv, na buzoq kartochkasi, na guruh soni o'zgargan
        self.assertEqual(
            (self.group.count, AnimalEvent.objects.count(), list(Animal.objects.values_list('tag_number', flat=True))),
            (3, 0, ['7']))

    def test_worker_can_open_cards(self):
        # Ishchi tug'ishni yozganda ham buzoq kartasiz qolmaydi
        self.client.force_authenticate(self.worker)
        r = self.calving([{'tag_number': '21'}], count=1)
        self.assertEqual(r.status_code, 201, r.content)
        self.group.refresh_from_db()
        self.assertEqual((self.group.count, Animal.objects.filter(tag_number='21').count()), (4, 1))

    def test_worker_can_still_record_birth_without_cards(self):
        self.client.force_authenticate(self.worker)
        r = self.calving(None, count=1)
        self.assertEqual(r.status_code, 201, r.content)
        self.group.refresh_from_db()
        self.assertEqual((self.group.count, Animal.objects.count()), (4, 0))

    def test_deleting_birth_keeps_cards_consistent(self):
        """Tug'ilish o'chirilganda guruh soni qaytadi, lekin ochilgan kartochkalar qoladi."""
        self.make_animal('1')
        event_id = self.calving([{'tag_number': '21'}], count=1).json()['id']
        self.assertEqual(self.client.delete(f'{EVENTS}{event_id}/').status_code, 204)
        self.group.refresh_from_db()
        self.assertEqual(self.group.count, 3)
        self.assertEqual(Animal.objects.filter(status='faol').count(), 2)  # 2 <= 3: sig'adi

    def test_cannot_delete_birth_while_its_cards_would_exceed_group_count(self):
        """3 ta hayvon, 3 ta kartochka bor; tug'ilish +1 va buzoq kartochkasi: o'chirsak kartochkalar soni oshib ketadi."""
        for tag in ('1', '2', '3'):
            self.make_animal(tag)
        event_id = self.calving([{'tag_number': '21'}], count=1).json()['id']
        r = self.client.delete(f'{EVENTS}{event_id}/')
        self.assertEqual(r.status_code, 400)
        self.assertIn('kartochkasini o', str(r.json()))
        self.group.refresh_from_db()
        self.assertEqual((self.group.count, AnimalEvent.objects.count(), Animal.objects.count()), (4, 1, 4))
        # Buzoq kartochkasi o'chirilgach, tug'ilishni o'chirish mumkin
        Animal.objects.filter(tag_number='21').delete()
        self.assertEqual(self.client.delete(f'{EVENTS}{event_id}/').status_code, 204)
        self.group.refresh_from_db()
        self.assertEqual(self.group.count, 3)

    def test_idempotent_retry_does_not_duplicate_cards(self):
        body = {'animal_group': self.group.pk, 'event_type': 'tugilish', 'title': 'Buzoq', 'animal_count': 1,
                'start_date': str(self.today), 'calves': [{'tag_number': '21'}]}
        first = self.client.post(EVENTS, body, format='json', headers={'Idempotency-Key': 'calf-key-0001'})
        second = self.client.post(EVENTS, body, format='json', headers={'Idempotency-Key': 'calf-key-0001'})
        self.assertEqual((first.status_code, second.status_code), (201, 201))
        self.assertEqual(second.headers.get('Idempotent-Replayed'), 'true')
        self.group.refresh_from_db()
        self.assertEqual((self.group.count, Animal.objects.count(), AnimalEvent.objects.count()), (4, 1, 1))


class PregnancyTests(AnimalCardBase):
    def patch(self, animal, **data):
        return self.client.patch(f'{CARDS}{animal.pk}/', data, format='json')

    def test_mark_pregnant_calculates_due_date(self):
        cow = self.make_animal('1')
        since = self.today - timedelta(days=30)
        r = self.patch(cow, pregnant_since=str(since))
        self.assertEqual(r.status_code, 200, r.content)
        body = r.json()
        self.assertTrue(body['is_pregnant'])
        self.assertEqual(body['due_date'], str(since + timedelta(days=283)))
        self.assertEqual(body['days_to_calving'], 253)

    def test_custom_due_date_and_clearing(self):
        cow = self.make_animal('2')
        due = self.today + timedelta(days=20)
        r = self.patch(cow, pregnant_since=str(self.today - timedelta(days=10)), due_date=str(due))
        self.assertEqual(r.json()['due_date'], str(due))
        r = self.patch(cow, pregnant_since=None)
        self.assertFalse(r.json()['is_pregnant'])
        self.assertIsNone(r.json()['due_date'])

    def test_validation(self):
        bull = self.make_animal('3', sex='erkak')
        self.assertEqual(self.patch(bull, pregnant_since=str(self.today)).status_code, 400)
        cow = self.make_animal('4')
        self.assertEqual(self.patch(cow, pregnant_since=str(self.today + timedelta(days=1))).status_code, 400)
        r = self.patch(cow, pregnant_since=str(self.today), due_date=str(self.today - timedelta(days=1)))
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.patch(cow, due_date=str(self.today)).status_code, 400)

    def test_birth_by_mother_ends_pregnancy(self):
        cow = self.make_animal('5', pregnant_since=self.today - timedelta(days=280), due_date=self.today)
        r = self.client.post(EVENTS, {'animal_group': self.group.pk, 'animal': cow.pk, 'event_type': 'tugilish',
                                      'title': "Tug'di", 'animal_count': 1, 'start_date': str(self.today)},
                             format='json')
        self.assertEqual(r.status_code, 201, r.content)
        cow.refresh_from_db()
        self.assertIsNone(cow.pregnant_since)
        self.assertIsNone(cow.due_date)

    def test_selling_ends_pregnancy(self):
        cow = self.make_animal('6', pregnant_since=self.today - timedelta(days=100),
                               due_date=self.today + timedelta(days=183))
        self.assertEqual(self.patch(cow, status='sotilgan').status_code, 200)
        cow.refresh_from_db()
        self.assertIsNone(cow.pregnant_since)

    def test_worker_cannot_mark(self):
        cow = self.make_animal('7')
        self.client.force_authenticate(self.worker)
        self.assertEqual(self.patch(cow, pregnant_since=str(self.today)).status_code, 403)

    def test_dashboard_summary_lists_soon_due(self):
        self.make_animal('8', pregnant_since=self.today - timedelta(days=275), due_date=self.today + timedelta(days=8))
        self.make_animal('9', pregnant_since=self.today - timedelta(days=100),
                         due_date=self.today + timedelta(days=183))
        r = self.client.get('/api/farms/summary/')
        self.assertEqual(r.status_code, 200)
        preg = r.json()['pregnancies']
        self.assertEqual(preg['count'], 1)
        self.assertEqual(preg['items'][0]['tag_number'], '8')
        self.assertEqual(preg['items'][0]['days_left'], 8)

    def test_gestation_days_by_type_name(self):
        from apps.animals.serializers import gestation_days
        self.assertEqual(gestation_days('Sigir'), 283)
        self.assertEqual(gestation_days("Qo\u02bby"), 150)
        self.assertEqual(gestation_days("Qo'y"), 150)
        self.assertIsNone(gestation_days('Tovuq'))

class DeleteBirthWithCalvesTests(AnimalCardBase):
    def calving(self, calves=None, count=2, **extra):
        data = {'animal_group': self.group.pk, 'event_type': 'tugilish', 'title': "Buzoqlar tug'ildi",
                'animal_count': count, 'start_date': str(self.today)}
        if calves is not None:
            data['calves'] = calves
        data.update(extra)
        return self.client.post(EVENTS, data, format='json')

    def test_delete_birth_with_calves_removes_cards_and_count(self):
        r = self.calving([{'tag_number': '31'}, {'tag_number': '32'}], count=2)
        event_id = r.json()['id']
        self.assertEqual(r.json()['newborn_cards'], 2)
        self.group.refresh_from_db()
        self.assertEqual(self.group.count, 5)
        self.assertEqual(self.client.delete(f'{EVENTS}{event_id}/?delete_calves=1').status_code, 204)
        self.group.refresh_from_db()
        self.assertEqual(self.group.count, 3)
        self.assertEqual(Animal.objects.count(), 0)

    def test_delete_calves_flag(self):
        for tag in ('1', '2', '3'):
            self.make_animal(tag)
        event_id = self.calving([{'tag_number': '41'}], count=1).json()['id']
        # bayroqsiz: kartochkalar soni guruh sonidan oshib ketadi, shuning uchun taqiqlanadi
        self.assertEqual(self.client.delete(f'{EVENTS}{event_id}/').status_code, 400)
        r = self.client.delete(f'{EVENTS}{event_id}/?delete_calves=1')
        self.assertEqual(r.status_code, 204, r.content)
        self.group.refresh_from_db()
        self.assertEqual(self.group.count, 3)
        self.assertFalse(Animal.objects.filter(tag_number='41').exists())
        self.assertEqual(Animal.objects.count(), 3)

    def test_manual_cards_are_not_touched(self):
        manual = self.make_animal('50', birth_date=self.today)
        event_id = self.calving([{'tag_number': '51'}], count=1).json()['id']
        self.assertEqual(self.client.delete(f'{EVENTS}{event_id}/?delete_calves=1').status_code, 204)
        self.assertTrue(Animal.objects.filter(pk=manual.pk).exists())
        self.assertFalse(Animal.objects.filter(tag_number='51').exists())

    def test_edit_event_text_and_date(self):
        event_id = self.calving(None, count=1).json()['id']
        r = self.client.patch(f'{EVENTS}{event_id}/', {'title': 'Yangi', 'description': 'Izoh'}, format='json')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()['title'], 'Yangi')


class TelegramNotifyTests(AnimalCardBase):
    def post_event(self, **extra):
        data = {'animal_group': self.group.pk, 'start_date': str(self.today), 'title': 'Yozuv'}
        data.update(extra)
        return self.client.post(EVENTS, data, format='json')

    def test_death_notifies_owner_even_when_owner_records(self):
        cow = self.make_animal('77', name='Oqtosh')
        with patch('apps.animals.views.notify_users') as notify:
            r = self.post_event(event_type='olim', animal=cow.pk, animal_count=1)
        self.assertEqual(r.status_code, 201, r.content)
        notify.assert_called_once()
        users, text = notify.call_args.args
        self.assertEqual(users, [self.owner])
        self.assertIn("O'lim", text)
        self.assertIn('№77', text)
        self.assertIn('Guruhda qoldi: 2 ta', text)

    def test_birth_notifies_with_cards(self):
        with patch('apps.animals.views.notify_users') as notify:
            r = self.post_event(event_type='tugilish', animal_count=2,
                                calves=[{'tag_number': '21'}, {'tag_number': '22'}])
        self.assertEqual(r.status_code, 201, r.content)
        notify.assert_called_once()
        text = notify.call_args.args[1]
        self.assertIn("Tug'ilish", text)
        self.assertIn('№21', text)
        self.assertIn('Guruhda endi: 5 ta', text)

    def test_worker_death_also_notifies_owner(self):
        self.client.force_authenticate(self.worker)
        with patch('apps.animals.views.notify_users') as notify:
            r = self.post_event(event_type='olim', animal_count=1)
        self.assertEqual(r.status_code, 201, r.content)
        self.assertIn('Kim: ishchi', notify.call_args.args[1])

    def test_other_events_do_not_notify(self):
        with patch('apps.animals.views.notify_users') as notify:
            self.post_event(event_type='kasallik', title='Mastit')
        notify.assert_not_called()


class AnimalStageTests(AnimalCardBase):
    """Davr (buzoq -> g'unajin -> sigir) yoshi va tug'ish/bug'ozlik tarixidan o'zi aniqlanadi."""

    def stage(self, animal):
        return self.client.get(f'{CARDS}{animal.pk}/').json()['stage']

    def born(self, months):
        return self.today - timedelta(days=30 * months + 3)

    def test_female_calf_is_buzoq(self):
        self.assertEqual(self.stage(self.make_animal('1', birth_date=self.born(5))), 'buzoq')

    def test_heifer_between_one_and_two_years(self):
        self.assertEqual(self.stage(self.make_animal('2', birth_date=self.born(16))), 'gunajin')

    def test_old_cow_without_history_is_sigir(self):
        self.assertEqual(self.stage(self.make_animal('3', birth_date=self.born(60))), 'sigir')

    def test_pregnancy_turns_heifer_into_sigir(self):
        heifer = self.make_animal('4', birth_date=self.born(16))
        self.assertEqual(self.stage(heifer), 'gunajin')
        r = self.client.patch(f'{CARDS}{heifer.pk}/', {'pregnant_since': str(self.today)}, format='json')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()['stage'], 'sigir')

    def test_birth_turns_heifer_into_sigir_and_calf_is_buzoq(self):
        heifer = self.make_animal('5', birth_date=self.born(20))
        r = self.client.post(EVENTS, {
            'animal_group': self.group.pk, 'event_type': 'tugilish', 'title': "Tug'di", 'animal_count': 1,
            'start_date': str(self.today), 'animal': heifer.pk, 'calves': [{'tag_number': '50'}]}, format='json')
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(self.stage(heifer), 'sigir')
        self.assertEqual(self.stage(Animal.objects.get(tag_number='50')), 'buzoq')

    def test_male_stages(self):
        self.assertEqual(self.stage(self.make_animal('6', sex='erkak', birth_date=self.born(3))), 'buzoq')
        self.assertEqual(self.stage(self.make_animal('7', sex='erkak', birth_date=self.born(30))), 'buqa')
