from datetime import timedelta
from decimal import Decimal

from apps.animals.models import MilkRecord
from apps.farms.models import Farm, Worker
from apps.finance.models import Transaction
from apps.tests.test_animals import AnimalCardBase, make_user

SALES = '/api/animals-milk-sale/'
STOCK = '/api/animals-milk-sale/stock/'
MILK = '/api/animals-milk/'


class MilkSaleTests(AnimalCardBase):
    def setUp(self):
        super().setUp()
        self.cow = self.make_animal('1', birth_date=self.today - timedelta(days=1500))
        MilkRecord.objects.create(animal=self.cow, date=self.today, session='ertalab', liters=Decimal('10'),
                                  recorded_by=self.owner)
        self.m2 = MilkRecord.objects.create(animal=self.cow, date=self.today, session='kechqurun',
                                            liters=Decimal('8'), recorded_by=self.owner)

    def sell(self, liters='12', price='4000', **extra):
        data = {'farm': self.farm.pk, 'date': str(self.today), 'liters': liters, 'price_per_liter': price}
        data.update(extra)
        return self.client.post(SALES, data, format='json')

    def stock(self):
        return self.client.get(STOCK, {'farm': self.farm.pk}).json()

    def test_stock_before_and_after_sale(self):
        s = self.stock()
        self.assertEqual((s['produced'], s['sold'], s['available']), ('18.0', '0.0', '18.0'))
        r = self.sell('12', '4000')
        self.assertEqual(r.status_code, 201, r.content)
        s = self.stock()
        self.assertEqual((s['sold'], s['available']), ('12.0', '6.0'))

    def test_sale_adds_income_to_balance(self):
        self.assertEqual(self.sell('12', '4000', note='Sutxona').status_code, 201)
        tx = Transaction.objects.get()
        self.assertEqual((tx.transaction_type, tx.category, tx.amount, tx.farm_id),
                         ('kirim', 'sotuv', Decimal('48000.00'), self.farm.pk))
        self.assertIn('Sutxona', tx.description)
        summary = self.client.get('/api/finance/summary/', {'farm': self.farm.pk}).json()
        self.assertEqual(Decimal(str(summary['balance'])), Decimal('48000'))

    def test_cannot_sell_more_than_stock(self):
        r = self.sell('19')
        self.assertEqual(r.status_code, 400)
        self.assertIn('liters', r.json())
        self.assertEqual(Transaction.objects.count(), 0)
        self.assertEqual(self.sell('18').status_code, 201)
        self.assertEqual(self.sell('0.5').status_code, 400)

    def test_validation(self):
        self.assertEqual(self.sell(price='0').status_code, 400)
        self.assertEqual(self.sell(liters='0').status_code, 400)
        self.assertEqual(self.sell(date=str(self.today + timedelta(days=1))).status_code, 400)

    def balance(self):
        summary = self.client.get('/api/finance/summary/', {'farm': self.farm.pk}).json()
        return Decimal(str(summary['balance']))

    def rows(self):
        data = self.client.get(SALES, {'farm': self.farm.pk}).json()
        return data['results'] if isinstance(data, dict) else data

    def test_deleting_sale_only_hides_the_record(self):
        sale_id = self.sell('12', '4000').json()['id']
        self.assertEqual(self.balance(), Decimal('48000'))

        self.assertEqual(self.client.delete(f'{SALES}{sale_id}/').status_code, 204)

        self.assertEqual(self.rows(), [])                       # yozuv ro'yxatdan yo'qoldi
        self.assertEqual(Transaction.objects.count(), 1)        # moliyadagi kirim qoldi
        self.assertEqual(self.balance(), Decimal('48000'))      # balans o'zgarmadi
        s = self.stock()
        self.assertEqual((s['sold'], s['available']), ('12.0', '6.0'))  # sotilgan sut hisobi ham o'zgarmadi

    def test_deleted_sale_cannot_be_deleted_or_cancelled_again(self):
        sale_id = self.sell('12').json()['id']
        self.client.delete(f'{SALES}{sale_id}/')
        self.assertEqual(self.client.delete(f'{SALES}{sale_id}/').status_code, 404)
        self.assertEqual(self.client.post(f'{SALES}{sale_id}/cancel/').status_code, 404)
        self.assertEqual(Transaction.objects.count(), 1)

    def test_hidden_sale_still_counts_when_selling_more(self):
        sale_id = self.sell('12').json()['id']
        self.client.delete(f'{SALES}{sale_id}/')
        self.assertEqual(self.sell('7').status_code, 400)       # 18 dan 12 sotilgan, 6 l qoldi
        self.assertEqual(self.sell('6').status_code, 201)

    def test_hidden_sale_keeps_milk_records_protected(self):
        sale_id = self.sell('12').json()['id']
        self.client.delete(f'{SALES}{sale_id}/')
        self.assertEqual(self.client.delete(f'{MILK}{self.m2.pk}/').status_code, 400)

    def test_cancel_sale_restores_stock_and_removes_income(self):
        sale_id = self.sell('12', '4000').json()['id']
        self.assertEqual(self.client.post(f'{SALES}{sale_id}/cancel/').status_code, 204)
        self.assertEqual(Transaction.objects.count(), 0)
        self.assertEqual(self.balance(), Decimal('0'))
        self.assertEqual(self.stock()['available'], '18.0')
        self.assertEqual(self.rows(), [])

    def test_worker_without_finance_right_cannot_delete_or_cancel(self):
        sale_id = self.sell('12').json()['id']
        self.client.force_authenticate(self.worker)
        self.assertEqual(self.client.delete(f'{SALES}{sale_id}/').status_code, 404)
        self.assertEqual(self.client.post(f'{SALES}{sale_id}/cancel/').status_code, 404)
        self.client.force_authenticate(self.owner)
        self.assertEqual(len(self.rows()), 1)
        self.assertEqual(Transaction.objects.count(), 1)

    def test_sold_milk_record_cannot_be_removed(self):
        self.sell('12')  # 18 l dan 12 l sotildi: 8 l li yozuvni o'chirsak, 10 l qoladi (12 dan kam)
        self.assertEqual(self.client.delete(f'{MILK}{self.m2.pk}/').status_code, 400)
        r = self.client.patch(f'{MILK}{self.m2.pk}/', {'liters': '1'}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.client.patch(f'{MILK}{self.m2.pk}/', {'liters': '3'}, format='json').status_code, 200)
        self.assertEqual(self.client.patch(f'{MILK}{self.m2.pk}/', {'liters': '9'}, format='json').status_code, 200)

    def test_unsold_milk_record_can_be_removed(self):
        self.assertEqual(self.client.delete(f'{MILK}{self.m2.pk}/').status_code, 204)
        self.assertEqual(self.stock()['available'], '10.0')

    def test_worker_permissions(self):
        self.client.force_authenticate(self.worker)
        s = self.client.get(STOCK, {'farm': self.farm.pk}).json()
        self.assertFalse(s['can_sell'])
        self.assertEqual(s['available'], '18.0')
        self.assertEqual(self.sell().status_code, 403)
        w = Worker.objects.get(user=self.worker)
        w.can_view_finance = True
        w.save()
        self.assertEqual(self.sell('5').status_code, 201)

    def test_other_farm_owner_has_no_access(self):
        other = make_user('boshqa')
        Farm.objects.create(owner=other, name='X', location='Y', farm_type='aralash')
        self.client.force_authenticate(other)
        self.assertEqual(self.client.get(STOCK, {'farm': self.farm.pk}).status_code, 403)
        self.assertEqual(self.sell().status_code, 403)
        self.assertEqual(self.client.get(SALES, {'farm': self.farm.pk}).json(), [])

    def test_list_and_no_edit(self):
        sale_id = self.sell('2').json()['id']
        rows = self.client.get(SALES, {'farm': self.farm.pk}).json()
        rows = rows['results'] if isinstance(rows, dict) else rows
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['amount'], '8000.00')
        self.assertEqual(self.client.patch(f'{SALES}{sale_id}/', {'liters': '1'}, format='json').status_code, 405)
