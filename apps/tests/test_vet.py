from decimal import Decimal

from django.test import override_settings

from apps.animals.models import AnimalEvent, MilkRecord
from apps.farms.models import Worker
from apps.inventory.models import InventoryItem
from apps.tests.test_animals import AnimalCardBase, make_user

EVENTS = '/api/animals-event/'
MILK = '/api/animals-milk/'
TXS = '/api/inventory-transaction/'
WORKERS = '/api/workers/'


@override_settings(TELEGRAM_ASYNC=False)
class VetTests(AnimalCardBase):
    def setUp(self):
        super().setUp()
        self.vet = make_user('vet', 'ishchi')
        self.vet_worker = Worker.objects.create(user=self.vet, farm=self.farm, kind='veterinar')
        self.cow = self.make_animal('1')

    def event(self, kind='davolash', **kw):
        data = {'animal_group': self.group.pk, 'animal': self.cow.pk, 'event_type': kind, 'title': 'Test',
                'start_date': str(self.today), **kw}
        return self.client.post(EVENTS, data, format='json')

    def test_vet_records_treatment_and_vaccine(self):
        self.client.force_authenticate(self.vet)
        self.assertEqual(self.event('davolash').status_code, 201)
        self.assertEqual(self.event('vaksinatsiya').status_code, 201)
        self.assertEqual(self.event('kasallik').status_code, 201)

    def test_vet_cannot_record_other_event_types(self):
        self.client.force_authenticate(self.vet)
        for kind in ('olim', 'vazn_olchash'):
            r = self.event(kind, animal_count=1)
            self.assertEqual(r.status_code, 403, kind)
        self.assertEqual(AnimalEvent.objects.count(), 0)

    def test_regular_worker_still_records_any_event(self):
        self.client.force_authenticate(self.worker)
        self.assertEqual(self.event('vazn_olchash').status_code, 201)

    def test_vet_cannot_add_milk(self):
        self.client.force_authenticate(self.vet)
        r = self.client.post(MILK, {'animal': self.cow.pk, 'date': str(self.today), 'session': 'ertalab',
                                    'liters': '10'}, format='json')
        self.assertEqual(r.status_code, 403)
        self.assertEqual(MilkRecord.objects.count(), 0)

    def test_vet_inventory_only_use(self):
        item = InventoryItem.objects.create(farm=self.farm, item_name='Antibiotik', item_type='dori',
                                            unit='dona', quantity=Decimal('10'), low_stock_threshold=Decimal('1'))
        self.client.force_authenticate(self.vet)
        add = self.client.post(TXS, {'inventory_item': item.pk, 'transaction_type': 'kirim', 'quantity': '5',
                                     'date': str(self.today)},
                               format='json')
        self.assertEqual(add.status_code, 403)
        use = self.client.post(TXS, {'inventory_item': item.pk, 'transaction_type': 'sarf', 'quantity': '1',
                                     'date': str(self.today)},
                               format='json')
        self.assertEqual(use.status_code, 201, use.content)

    def test_vet_cannot_see_finance(self):
        from apps.finance.models import Transaction
        Transaction.objects.create(farm=self.farm, transaction_type='kirim', category='sotuv', amount=Decimal('1000'),
                                   date=self.today, recorded_by=self.owner)
        self.client.force_authenticate(self.vet)
        r = self.client.get('/api/finance/', {'farm': self.farm.pk})
        rows = r.json()['results'] if isinstance(r.json(), dict) else r.json()
        self.assertEqual(rows, [])
        summary = self.client.get('/api/finance/summary/', {'farm': self.farm.pk}).json()
        self.assertEqual(Decimal(str(summary['balance'])), 0)

    def test_owner_creates_vet_without_finance(self):
        r = self.client.post(WORKERS, {'farm': self.farm.pk, 'username': 'vet2', 'password': 'Kuchli-Parol-2026',
                                       'first_name': 'Doktor', 'kind': 'veterinar', 'can_view_finance': True},
                             format='json')
        self.assertEqual(r.status_code, 201, r.content)
        w = Worker.objects.get(user__username='vet2')
        self.assertEqual((w.kind, w.can_view_finance), ('veterinar', False))

    def test_cannot_give_finance_to_vet(self):
        r = self.client.patch(f'{WORKERS}{self.vet_worker.pk}/', {'can_view_finance': True}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_my_role_in_farm(self):
        self.assertEqual(self.client.get(f'/api/farms/{self.farm.pk}/').json()['my_role'], 'owner')
        self.client.force_authenticate(self.vet)
        self.assertEqual(self.client.get(f'/api/farms/{self.farm.pk}/').json()['my_role'], 'veterinar')
        self.client.force_authenticate(self.worker)
        self.assertEqual(self.client.get(f'/api/farms/{self.farm.pk}/').json()['my_role'], 'ishchi')


@override_settings(TELEGRAM_ASYNC=False)
class HistoryPdfTests(AnimalCardBase):
    URL = '/api/animals-event/history-pdf/'

    def test_pdf_with_records(self):
        cow = self.make_animal('1')
        AnimalEvent.objects.create(animal_group=self.group, animal=cow, event_type='davolash', title="Oyoq davosi",
                                   start_date=self.today, recorded_by=self.owner)
        r = self.client.get(self.URL, {'farm': self.farm.pk, 'animal': cow.pk})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r['Content-Type'], 'application/pdf')
        self.assertTrue(r.content.startswith(b'%PDF'))

    def test_pdf_empty_period(self):
        r = self.client.get(self.URL, {'farm': self.farm.pk, 'date_from': '2020-01-01', 'date_to': '2020-01-31'})
        self.assertEqual(r.status_code, 200)

    def test_stranger_forbidden(self):
        self.client.force_authenticate(make_user('begona'))
        self.assertEqual(self.client.get(self.URL, {'farm': self.farm.pk}).status_code, 403)

    def test_bad_date(self):
        self.assertEqual(self.client.get(self.URL, {'farm': self.farm.pk, 'date_from': 'x'}).status_code, 400)
        