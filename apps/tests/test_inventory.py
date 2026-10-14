from decimal import Decimal

from rest_framework.test import APITestCase

from apps.farms.models import Farm, Worker
from apps.finance.models import Transaction
from apps.inventory.models import InventoryItem, InventoryTransaction
from apps.users.models import User

ITEMS = '/api/inventory-item/'
TXS = '/api/inventory-transaction/'


def make_user(username, role='fermer'):
    return User.objects.create_user(username=username, password='Kuchli-Parol-2026', role=role)


class InventoryBalanceTests(APITestCase):
    """Ombor kirimi narxi moliyada chiqim bo'lib, balansdan ayrilishi kerak."""

    def setUp(self):
        self.owner = make_user('egasi')
        self.farm = Farm.objects.create(owner=self.owner, name='Baraka', location='Qarshi', farm_type='aralash')
        self.client.force_authenticate(self.owner)

    def balance(self):
        r = self.client.get('/api/finance/summary/', {'farm': self.farm.pk})
        self.assertEqual(r.status_code, 200)
        return Decimal(str(r.json()['balance']))

    def new_item(self, **extra):
        data = {'farm': self.farm.pk, 'item_name': 'Silos', 'item_type': 'ozuqa', 'unit': 'tonna',
                'quantity': '30', 'low_stock_threshold': '5'}
        data.update(extra)
        return self.client.post(ITEMS, data, format='json')

    # --- yangi mahsulot boshlang'ich zaxira bilan
    def test_new_item_with_price_reduces_balance(self):
        r = self.new_item(initial_amount='15000000')
        self.assertEqual(r.status_code, 201, r.content)
        self.assertNotIn('initial_amount', r.json())
        item = InventoryItem.objects.get()
        self.assertEqual(item.quantity, 30)

        inv_tx = InventoryTransaction.objects.get()
        self.assertEqual((inv_tx.transaction_type, inv_tx.quantity, inv_tx.amount), ('kirim', 30, 15000000))
        fin = Transaction.objects.get()
        self.assertEqual((fin.transaction_type, fin.category, fin.amount), ('chiqim', 'ozuqa', 15000000))
        self.assertEqual(inv_tx.finance_transaction_id, fin.pk)
        self.assertEqual(self.balance(), Decimal('-15000000'))

    def test_new_item_without_price_logs_stock_but_no_expense(self):
        self.assertEqual(self.new_item().status_code, 201)
        self.assertEqual(InventoryTransaction.objects.count(), 1)  # tarixda ko'rinadi
        self.assertEqual(Transaction.objects.count(), 0)
        self.assertEqual(self.balance(), 0)

    def test_new_item_with_zero_stock_logs_nothing(self):
        self.assertEqual(self.new_item(quantity='0').status_code, 201)
        self.assertEqual(InventoryTransaction.objects.count(), 0)

    def test_price_without_stock_rejected(self):
        r = self.new_item(quantity='0', initial_amount='1000')
        self.assertEqual(r.status_code, 400)
        self.assertEqual(InventoryItem.objects.count(), 0)

    def test_bad_price_rejected(self):
        self.assertEqual(self.new_item(initial_amount='-5').status_code, 400)
        self.assertEqual(self.new_item(initial_amount='0').status_code, 400)
        self.assertEqual(InventoryItem.objects.count(), 0)

    def test_worker_cannot_create_item(self):
        worker = make_user('ishchi', 'ishchi')
        Worker.objects.create(user=worker, farm=self.farm, can_view_finance=True)
        self.client.force_authenticate(worker)
        self.assertEqual(self.new_item(initial_amount='1000').status_code, 403)
        self.assertEqual(Transaction.objects.count(), 0)

    def test_update_ignores_initial_amount(self):
        self.new_item(initial_amount='100')
        item = InventoryItem.objects.get()
        r = self.client.patch(f'{ITEMS}{item.pk}/', {'initial_amount': '999', 'low_stock_threshold': '7'},
                              format='json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Transaction.objects.count(), 1)

    # --- oddiy kirim (oldindan ishlagan qism: regressiya himoyasi)
    def test_kirim_with_price_reduces_balance_and_delete_restores(self):
        self.new_item(quantity='0')
        item = InventoryItem.objects.get()
        r = self.client.post(TXS, {'inventory_item': item.pk, 'transaction_type': 'kirim', 'quantity': '10',
                                   'date': '2026-10-14', 'amount': '4000000'}, format='json')
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(self.balance(), Decimal('-4000000'))
        self.client.delete(f"{TXS}{r.json()['id']}/")
        self.assertEqual(self.balance(), 0)
        self.assertEqual(Transaction.objects.count(), 0)

    def test_worker_without_finance_cannot_send_price(self):
        self.new_item()
        item = InventoryItem.objects.get()
        worker = make_user('ishchi2', 'ishchi')
        Worker.objects.create(user=worker, farm=self.farm, can_view_finance=False)
        self.client.force_authenticate(worker)
        r = self.client.post(TXS, {'inventory_item': item.pk, 'transaction_type': 'kirim', 'quantity': '1',
                                   'date': '2026-10-14', 'amount': '1000'}, format='json')
        self.assertEqual(r.status_code, 400)
        ok = self.client.post(TXS, {'inventory_item': item.pk, 'transaction_type': 'kirim', 'quantity': '1',
                                    'date': '2026-10-14'}, format='json')
        self.assertEqual(ok.status_code, 201)  # narxsiz kirim ishchi uchun ruxsat etilgan

