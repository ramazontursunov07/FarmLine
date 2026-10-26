from datetime import timedelta
from decimal import Decimal

from apps.animals.models import MilkRecord, MilkSale
from apps.debts.models import Party
from apps.farms.models import Farm, Worker
from apps.tests.test_animals import AnimalCardBase, make_user

SALES = '/api/animals-milk-sale/'
SALE = SALES


class CustomerTests(AnimalCardBase):
    def setUp(self):
        super().setUp()
        self.cow = self.make_animal('1', birth_date=self.today - timedelta(days=1500))
        MilkRecord.objects.create(animal=self.cow, date=self.today, session='ertalab', liters=Decimal('200'),
                                  recorded_by=self.owner)

    def sell(self, **kw):
        data = {'farm': self.farm.pk, 'date': str(self.today), 'liters': '10', 'price_per_liter': '5000', **kw}
        return self.client.post(SALES, data, format='json')

    def test_cash_sale_creates_customer_by_name(self):
        r = self.sell(customer_name='Karim aka')
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.json()['customer_name'], 'Karim aka')
        self.assertEqual(Party.objects.get().kind, 'mijoz')

    def test_same_name_reuses_customer(self):
        self.sell(customer_name='Karim aka')
        self.sell(customer_name='karim aka', liters='5')
        self.assertEqual(Party.objects.count(), 1)

    def test_sale_without_customer_still_works(self):
        self.assertEqual(self.sell().status_code, 201)
        self.assertIsNone(MilkSale.objects.get().customer)

    def test_credit_sale_links_debtor_as_customer(self):
        r = self.sell(on_credit=True, party_name='Salim')
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(MilkSale.objects.get().customer.name, 'Salim')

    def test_customers_summary(self):
        self.sell(customer_name='Karim aka')
        self.sell(customer_name='Karim aka', liters='5', date=str(self.today))
        self.sell(on_credit=True, party_name='Salim', liters='20')  # 100 000 qarz
        rows = {r['name']: r for r in self.client.get(f'{SALE}customers/?farm={self.farm.pk}').json()}
        self.assertEqual(rows['Karim aka']['liters'], '15.0')
        self.assertEqual(Decimal(rows['Karim aka']['revenue']), Decimal('75000'))
        self.assertEqual(rows['Karim aka']['sales'], 2)
        self.assertEqual(rows['Karim aka']['last_date'], str(self.today))
        self.assertEqual(Decimal(rows['Karim aka']['debt']), Decimal('0'))
        self.assertEqual(Decimal(rows['Salim']['debt']), Decimal('100000'))

    def test_hidden_sale_still_counted(self):
        self.sell(customer_name='Karim aka')
        MilkSale.objects.update(is_hidden=True)
        rows = self.client.get(f'{SALE}customers/?farm={self.farm.pk}').json()
        self.assertEqual(rows[0]['liters'], '10.0')

    def test_other_farm_customer_id_rejected(self):
        other = Farm.objects.create(owner=self.owner, name='Boshqa', location='X', farm_type='aralash')
        p = Party.objects.create(farm=other, kind='mijoz', name='Begona')
        self.assertEqual(self.sell(customer=p.pk).status_code, 400)

    def test_worker_without_finance_cannot_see_customers(self):
        w = make_user('ali', 'ishchi')
        Worker.objects.create(user=w, farm=self.farm, can_view_finance=False)
        self.client.force_authenticate(w)
        self.assertEqual(self.client.get(f'{SALE}customers/?farm={self.farm.pk}').status_code, 403)
