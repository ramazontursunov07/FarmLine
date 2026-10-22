from datetime import timedelta
from decimal import Decimal

from apps.animals.models import AnimalGroup, MilkRecord
from apps.debts.models import Debt, DebtPayment, Party
from apps.finance.models import Transaction
from apps.inventory.models import InventoryItem
from apps.tests.test_animals import AnimalCardBase

SALES = '/api/animals-milk-sale/'
TXS = '/api/inventory-transaction/'
FINANCE = '/api/finance/'
PAYMENTS = '/api/debt-payment/'
DEBTS = '/api/debt/'


class CreditBase(AnimalCardBase):
    def balance(self):
        s = self.client.get('/api/finance/summary/', {'farm': self.farm.pk}).json()
        return Decimal(str(s['balance']))

    def credit(self, **extra):
        data = {'on_credit': True, 'party_name': 'Sutxona', 'due_date': str(self.today + timedelta(days=7))}
        data.update(extra)
        return data


class MilkCreditTests(CreditBase):
    def setUp(self):
        super().setUp()
        self.cow = self.make_animal('1', birth_date=self.today - timedelta(days=1500))
        MilkRecord.objects.create(animal=self.cow, date=self.today, session='ertalab', liters=Decimal('20'),
                                  recorded_by=self.owner)

    def sell(self, **extra):
        data = {'farm': self.farm.pk, 'date': str(self.today), 'liters': '10', 'price_per_liter': '4000'}
        data.update(extra)
        return self.client.post(SALES, data, format='json')

    def test_credit_sale_opens_debt_without_changing_balance(self):
        r = self.sell(**self.credit())
        self.assertEqual(r.status_code, 201, r.content)
        self.assertTrue(r.json()['on_credit'])
        self.assertEqual(r.json()['party_name'], 'Sutxona')
        self.assertEqual(Transaction.objects.count(), 0)
        self.assertEqual(self.balance(), 0)
        debt = Debt.objects.get()
        self.assertEqual((debt.amount, debt.party.kind, debt.affects_balance), (Decimal('40000.00'), 'mijoz', True))
        # sut ombordan ayrildi
        stock = self.client.get(SALES + 'stock/', {'farm': self.farm.pk}).json()
        self.assertEqual(stock['sold'], '10.0')

    def test_payment_adds_income_to_balance(self):
        self.sell(**self.credit())
        debt = Debt.objects.get()
        r = self.client.post(PAYMENTS, {'debt': debt.pk, 'amount': '15000', 'date': str(self.today)}, format='json')
        self.assertEqual(r.status_code, 201, r.content)
        tx = Transaction.objects.get()
        self.assertEqual((tx.transaction_type, tx.category, tx.amount), ('kirim', 'sotuv', Decimal('15000.00')))
        self.assertEqual(self.balance(), 15000)
        # to'lovni o'zgartirsak / o'chirsak, balans ham mos o'zgaradi
        pay = DebtPayment.objects.get()
        self.client.patch(f'{PAYMENTS}{pay.pk}/', {'amount': '20000'}, format='json')
        self.assertEqual(self.balance(), 20000)
        self.client.delete(f'{PAYMENTS}{pay.pk}/')
        self.assertEqual(self.balance(), 0)

    def test_upfront_part_is_paid_immediately(self):
        r = self.sell(**self.credit(paid_now='10000'))
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(self.balance(), 10000)
        self.assertEqual(r.json()['debt_remaining'], '30000.00')

    def test_cancel_sale_removes_debt_and_money(self):
        sale = self.sell(**self.credit(paid_now='10000')).json()
        self.assertEqual(self.client.post(f'{SALES}{sale["id"]}/cancel/').status_code, 204)
        self.assertEqual(Debt.objects.count(), 0)
        self.assertEqual(Transaction.objects.count(), 0)
        self.assertEqual(self.balance(), 0)

    def test_existing_party_can_be_chosen(self):
        party = Party.objects.create(farm=self.farm, kind='mijoz', name='Ali')
        r = self.sell(on_credit=True, party=party.pk)
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(Debt.objects.get().party_id, party.pk)

    def test_credit_needs_a_person(self):
        r = self.sell(on_credit=True)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(Debt.objects.count(), 0)

    def test_upfront_must_be_less_than_total(self):
        r = self.sell(**self.credit(paid_now='40000'))
        self.assertEqual(r.status_code, 400)
        self.assertEqual(Debt.objects.count(), 0)

    def test_due_date_cannot_precede_sale(self):
        r = self.sell(**self.credit(due_date=str(self.today - timedelta(days=1))))
        self.assertEqual(r.status_code, 400)

    def test_cash_sale_still_works(self):
        self.assertEqual(self.sell().status_code, 201)
        self.assertEqual(self.balance(), 40000)
        self.assertEqual(Debt.objects.count(), 0)

    def test_manual_debt_payment_does_not_touch_balance(self):
        party = Party.objects.create(farm=self.farm, kind='mijoz', name='Ali')
        debt = Debt.objects.create(farm=self.farm, party=party, amount=Decimal('1000'), date=self.today)
        self.client.post(PAYMENTS, {'debt': debt.pk, 'amount': '500', 'date': str(self.today)}, format='json')
        self.assertEqual(Transaction.objects.count(), 0)


class InventoryCreditTests(CreditBase):
    def setUp(self):
        super().setUp()
        self.item = InventoryItem.objects.create(farm=self.farm, item_name='Omuxta', item_type='ozuqa',
                                                 quantity=0, unit='kg')

    def buy(self, **extra):
        data = {'inventory_item': self.item.pk, 'transaction_type': 'kirim', 'quantity': '100',
                'amount': '500000', 'date': str(self.today)}
        data.update(extra)
        return self.client.post(TXS, data, format='json')

    def test_credit_purchase_opens_payable_debt_and_adds_stock(self):
        r = self.buy(**self.credit(party_name='Yem do\'koni'))
        self.assertEqual(r.status_code, 201, r.content)
        self.assertTrue(r.json()['on_credit'])
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, Decimal('100'))
        self.assertEqual(Transaction.objects.count(), 0)
        debt = Debt.objects.get()
        self.assertEqual((debt.party.kind, debt.amount, debt.balance_category),
                         ('taminotchi', Decimal('500000.00'), 'ozuqa'))

    def test_paying_supplier_creates_expense(self):
        self.buy(**self.credit())
        debt = Debt.objects.get()
        self.client.post(PAYMENTS, {'debt': debt.pk, 'amount': '200000', 'date': str(self.today)}, format='json')
        tx = Transaction.objects.get()
        self.assertEqual((tx.transaction_type, tx.category, tx.amount), ('chiqim', 'ozuqa', Decimal('200000.00')))
        self.assertEqual(self.balance(), -200000)

    def test_deleting_purchase_removes_debt(self):
        tx_id = self.buy(**self.credit(paid_now='100000')).json()['id']
        self.assertEqual(self.client.delete(f'{TXS}{tx_id}/').status_code, 204)
        self.assertEqual(Debt.objects.count(), 0)
        self.assertEqual(Transaction.objects.count(), 0)

    def test_credit_requires_price(self):
        r = self.buy(amount=None, **self.credit())
        self.assertEqual(r.status_code, 400)

    def test_credit_not_for_consumption(self):
        self.item.quantity = 50
        self.item.save()
        r = self.buy(transaction_type='sarf', **self.credit())
        self.assertEqual(r.status_code, 400)


class FinanceCreditTests(CreditBase):
    def test_credit_animal_sale_reduces_group_but_not_balance(self):
        r = self.client.post(FINANCE, {
            'farm': self.farm.pk, 'transaction_type': 'kirim', 'category': 'sotuv', 'amount': '9000000',
            'date': str(self.today), 'animal_group': self.group.pk, 'animal_count': 2,
            **self.credit(party_name='Bozorchi')},
                             format='json')
        self.assertEqual(r.status_code, 201, r.content)
        self.group.refresh_from_db()
        self.assertEqual(self.group.count, 1)
        self.assertEqual(Transaction.objects.count(), 0)
        debt = Debt.objects.get()
        self.assertEqual((debt.animal_count, debt.party.kind), (2, 'mijoz'))
        # qarz o'chirilsa hayvonlar qaytadi
        self.assertEqual(self.client.delete(f'{DEBTS}{debt.pk}/').status_code, 204)
        self.group.refresh_from_db()
        self.assertEqual(self.group.count, 3)

    def test_credit_expense_opens_payable(self):
        r = self.client.post(FINANCE, {
            'farm': self.farm.pk, 'transaction_type': 'chiqim', 'category': 'kommunal', 'amount': '300000',
            'date': str(self.today), **self.credit(party_name='Elektr')}, format='json')
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(Debt.objects.get().party.kind, 'taminotchi')
        self.assertEqual(self.balance(), 0)

    def test_too_many_animals_on_credit_rejected(self):
        r = self.client.post(FINANCE, {
            'farm': self.farm.pk, 'transaction_type': 'kirim', 'category': 'sotuv', 'amount': '9000000',
            'date': str(self.today), 'animal_group': self.group.pk, 'animal_count': 9, **self.credit()}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertEqual(Debt.objects.count(), 0)
