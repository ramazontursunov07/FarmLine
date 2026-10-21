from datetime import date, timedelta
from decimal import Decimal

from django.utils import timezone
from rest_framework.test import APITestCase

from apps.debts.models import Debt, DebtPayment, Party
from apps.farms.models import Farm, Worker
from apps.users.alerts import build_alert_lines, debt_lines
from apps.users.models import User

PARTIES = '/api/debt-party/'
DEBTS = '/api/debt/'
PAYMENTS = '/api/debt-payment/'


def rows(response):
    data = response.json()
    return data['results'] if isinstance(data, dict) else data


def make_user(username, role='fermer'):
    return User.objects.create_user(username=username, password='Kuchli-Parol-2026', role=role)


class DebtBase(APITestCase):
    def setUp(self):
        self.owner = make_user('egasi')
        self.farm = Farm.objects.create(owner=self.owner, name='Baraka', location='Qarshi', farm_type='aralash')
        self.today = timezone.localdate()
        self.client.force_authenticate(self.owner)

    def party(self, name='Ali', kind='mijoz', farm=None):
        return Party.objects.create(farm=farm or self.farm, name=name, kind=kind)

    def debt(self, party, amount=1000, due_in=None, days_ago=10, **extra):
        due = None if due_in is None else self.today + timedelta(days=due_in)
        return Debt.objects.create(farm=party.farm, party=party, amount=Decimal(amount),
                                   date=self.today - timedelta(days=days_ago), due_date=due, **extra)

    def pay(self, debt, amount):
        return self.client.post(PAYMENTS, {'debt': debt.pk, 'amount': amount, 'date': str(self.today)}, format='json')


class PartyTests(DebtBase):
    def test_create_and_list_with_totals(self):
        r = self.client.post(PARTIES, {'farm': self.farm.pk, 'name': 'Ali', 'phone': '+998901112233'}, format='json')
        self.assertEqual(r.status_code, 201, r.content)
        ali = Party.objects.get()
        self.debt(ali, 1000, due_in=-2)
        d2 = self.debt(ali, 500, due_in=5)
        self.pay(d2, 200)
        body = rows(self.client.get(PARTIES, {'farm': self.farm.pk}))[0]
        self.assertEqual(body['totals']['amount'], '1500.00')
        self.assertEqual(body['totals']['paid'], '200.00')
        self.assertEqual(body['totals']['remaining'], '1300.00')
        self.assertEqual((body['totals']['overdue_count'], body['totals']['overdue_amount']), (1, '1000.00'))

    def test_totals_not_doubled_by_several_payments(self):
        d = self.debt(self.party(), 1000)
        self.pay(d, 100)
        self.pay(d, 150)
        self.debt(Party.objects.get(), 300)
        totals = rows(self.client.get(PARTIES))[0]['totals']
        self.assertEqual((totals['amount'], totals['paid'], totals['remaining']), ('1300.00', '250.00', '1050.00'))

    def test_duplicate_name_rejected_but_same_name_other_kind_ok(self):
        self.party('Ali', 'mijoz')
        r = self.client.post(PARTIES, {'farm': self.farm.pk, 'name': 'ali', 'kind': 'mijoz'}, format='json')
        self.assertEqual(r.status_code, 400)
        r = self.client.post(PARTIES, {'farm': self.farm.pk, 'name': 'Ali', 'kind': 'taminotchi'}, format='json')
        self.assertEqual(r.status_code, 201, r.content)

    def test_kind_filter(self):
        self.party('Ali', 'mijoz')
        self.party('Yem zavodi', 'taminotchi')
        names = [p['name'] for p in rows(self.client.get(PARTIES, {'kind': 'taminotchi'}))]
        self.assertEqual(names, ['Yem zavodi'])

    def test_cannot_delete_party_with_debts(self):
        ali = self.party()
        self.debt(ali)
        self.assertEqual(self.client.delete(f'{PARTIES}{ali.pk}/').status_code, 400)
        self.assertTrue(Party.objects.filter(pk=ali.pk).exists())
        empty = self.party('Bo\'sh')
        self.assertEqual(self.client.delete(f'{PARTIES}{empty.pk}/').status_code, 204)


class DebtTests(DebtBase):
    def create(self, party, **extra):
        data = {'party': party.pk, 'amount': '800000', 'date': str(self.today),
                'due_date': str(self.today + timedelta(days=7)), 'description': '120 litr sut'}
        data.update(extra)
        return self.client.post(DEBTS, data, format='json')

    def test_create_sets_farm_and_computes_fields(self):
        r = self.create(self.party())
        self.assertEqual(r.status_code, 201, r.content)
        body = r.json()
        self.assertEqual(body['farm'], self.farm.pk)
        self.assertEqual((body['paid'], body['remaining'], body['kind']), ('0.00', '800000.00', 'mijoz'))
        self.assertFalse(body['is_overdue'])

    def test_validation(self):
        ali = self.party()
        self.assertEqual(self.create(ali, amount='0').status_code, 400)
        self.assertEqual(self.create(ali, date=str(self.today + timedelta(days=1))).status_code, 400)
        self.assertEqual(self.create(ali, due_date=str(self.today - timedelta(days=1))).status_code, 400)

    def test_overdue_flag_and_days(self):
        d = self.debt(self.party(), 1000, due_in=-4)
        body = self.client.get(f'{DEBTS}{d.pk}/').json()
        self.assertTrue(body['is_overdue'])
        self.assertEqual(body['days_overdue'], 4)

    def test_paid_debt_is_not_overdue(self):
        d = self.debt(self.party(), 1000, due_in=-4)
        self.pay(d, 1000)
        body = self.client.get(f'{DEBTS}{d.pk}/').json()
        self.assertFalse(body['is_overdue'])
        self.assertEqual(body['remaining'], '0.00')

    def test_status_filters(self):
        ali = self.party()
        open_debt = self.debt(ali, 1000, due_in=5)
        late = self.debt(ali, 1000, due_in=-3)
        closed = self.debt(ali, 1000, due_in=-3)
        self.pay(closed, 1000)
        ids = lambda status: sorted(d['id'] for d in rows(self.client.get(DEBTS, {'status': status})))
        self.assertEqual(ids('open'), sorted([open_debt.pk, late.pk]))
        self.assertEqual(ids('overdue'), [late.pk])
        self.assertEqual(ids('closed'), [closed.pk])
        self.assertEqual(self.client.get(DEBTS, {'status': 'x'}).status_code, 400)

    def test_cannot_lower_amount_below_paid(self):
        d = self.debt(self.party(), 1000)
        self.pay(d, 600)
        r = self.client.patch(f'{DEBTS}{d.pk}/', {'amount': '500'}, format='json')
        self.assertEqual(r.status_code, 400)
        r = self.client.patch(f'{DEBTS}{d.pk}/', {'amount': '700'}, format='json')
        self.assertEqual(r.status_code, 200, r.content)

    def test_delete_removes_payments(self):
        d = self.debt(self.party(), 1000)
        self.pay(d, 100)
        self.assertEqual(self.client.delete(f'{DEBTS}{d.pk}/').status_code, 204)
        self.assertEqual(DebtPayment.objects.count(), 0)

    def test_summary_splits_receivable_and_payable(self):
        ali = self.party('Ali', 'mijoz')
        zavod = self.party('Zavod', 'taminotchi')
        d = self.debt(ali, 1000, due_in=-1)
        self.pay(d, 400)
        self.debt(zavod, 5000, due_in=10)
        body = self.client.get(f'{DEBTS}summary/', {'farm': self.farm.pk}).json()
        self.assertEqual(body['receivable']['remaining'], '600.00')
        self.assertEqual((body['receivable']['overdue_count'], body['receivable']['overdue_amount']), (1, '600.00'))
        self.assertEqual(body['payable']['remaining'], '5000.00')
        self.assertEqual(body['payable']['overdue_count'], 0)
        self.assertEqual(self.client.get(f'{DEBTS}summary/').status_code, 400)

    def test_overview_for_dashboard(self):
        self.debt(self.party('Ali'), 1000, due_in=-2)
        self.debt(self.party('Vali'), 500, due_in=3)
        body = self.client.get(f'{DEBTS}overview/').json()
        self.assertEqual(len(body), 1)
        self.assertEqual((body[0]['farm'], body[0]['overdue_count'], body[0]['receivable_remaining']),
                         (self.farm.pk, 1, '1500.00'))


class PaymentTests(DebtBase):
    def test_partial_then_full_payment(self):
        d = self.debt(self.party(), 1000)
        self.assertEqual(self.pay(d, 400).status_code, 201)
        self.assertEqual(self.pay(d, 600).status_code, 201)
        self.assertEqual(self.client.get(f'{DEBTS}{d.pk}/').json()['remaining'], '0.00')

    def test_overpayment_rejected(self):
        d = self.debt(self.party(), 1000)
        self.pay(d, 700)
        r = self.pay(d, 400)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(DebtPayment.objects.count(), 1)
        self.pay(d, 300)
        self.assertEqual(self.pay(d, 1).status_code, 400)  # to'liq to'langan

    def test_invalid_payments(self):
        d = self.debt(self.party(), 1000, days_ago=5)
        self.assertEqual(self.pay(d, 0).status_code, 400)
        r = self.client.post(PAYMENTS, {'debt': d.pk, 'amount': 10, 'date': str(self.today + timedelta(days=1))},
                             format='json')
        self.assertEqual(r.status_code, 400)
        r = self.client.post(PAYMENTS, {'debt': d.pk, 'amount': 10, 'date': str(self.today - timedelta(days=9))},
                             format='json')
        self.assertEqual(r.status_code, 400)  # qarz berilmasdan oldin

    def test_edit_and_delete_payment(self):
        d = self.debt(self.party(), 1000)
        p = DebtPayment.objects.create(debt=d, amount=Decimal('400'), date=self.today)
        DebtPayment.objects.create(debt=d, amount=Decimal('500'), date=self.today)
        self.assertEqual(self.client.patch(f'{PAYMENTS}{p.pk}/', {'amount': '600'}, format='json').status_code, 400)
        self.assertEqual(self.client.patch(f'{PAYMENTS}{p.pk}/', {'amount': '500'}, format='json').status_code, 200)
        self.assertEqual(self.client.delete(f'{PAYMENTS}{p.pk}/').status_code, 204)
        self.assertEqual(self.client.get(f'{DEBTS}{d.pk}/').json()['remaining'], '500.00')


class PermissionTests(DebtBase):
    def setUp(self):
        super().setUp()
        self.worker = make_user('ishchi', 'ishchi')
        self.link = Worker.objects.create(user=self.worker, farm=self.farm)
        self.stranger = make_user('begona')

    def test_worker_without_finance_access_sees_nothing_and_cannot_write(self):
        d = self.debt(self.party())
        self.client.force_authenticate(self.worker)
        self.assertEqual(rows(self.client.get(DEBTS)), [])
        self.assertEqual(rows(self.client.get(PARTIES)), [])
        r = self.client.post(DEBTS, {'party': d.party.pk, 'amount': 5, 'date': str(self.today)}, format='json')
        self.assertEqual(r.status_code, 403)
        self.assertEqual(Debt.objects.count(), 1)

    def test_worker_with_finance_access_can_work(self):
        self.link.can_view_finance = True
        self.link.save()
        ali = self.party()
        self.client.force_authenticate(self.worker)
        r = self.client.post(DEBTS, {'party': ali.pk, 'amount': 500, 'date': str(self.today)}, format='json')
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(Debt.objects.get().recorded_by_id, self.worker.pk)

    def test_stranger_cannot_see_or_touch(self):
        d = self.debt(self.party())
        self.client.force_authenticate(self.stranger)
        self.assertEqual(rows(self.client.get(DEBTS)), [])
        self.assertEqual(self.client.get(f'{DEBTS}{d.pk}/').status_code, 404)
        self.assertEqual(self.client.delete(f'{DEBTS}{d.pk}/').status_code, 404)
        self.assertEqual(self.pay(d, 10).status_code, 403)
        self.assertEqual(DebtPayment.objects.count(), 0)
        self.assertEqual(self.client.get(f'{DEBTS}summary/', {'farm': self.farm.pk}).status_code, 403)


class DebtAlertTests(DebtBase):
    def lines(self):
        return "\n".join(debt_lines(self.farm, self.today))

    def test_overdue_and_soon_are_listed_far_ones_are_not(self):
        self.debt(self.party('Ali'), 500000, due_in=-7)
        self.debt(self.party('Vali'), 100000, due_in=2)
        self.debt(self.party('Sher'), 100000, due_in=30)
        text = self.lines()
        self.assertIn("Mijozlardan to'lov kutilmoqda: 2 ta, jami 600 000", text)
        self.assertIn("Ali — 500 000 so'm, 7 kun kechikdi", text)
        self.assertIn("Vali", text)
        self.assertNotIn("Sher", text)

    def test_payable_has_its_own_block(self):
        self.debt(self.party('Zavod', 'taminotchi'), 2000000, due_in=-1)
        text = self.lines()
        self.assertIn("Yetkazib beruvchilarga to'lash kerak: 1 ta", text)
        self.assertNotIn("Mijozlardan", text)

    def test_one_line_per_person_with_remaining_amount(self):
        ali = self.party('Ali')
        d1 = self.debt(ali, 1000, due_in=-5)
        self.debt(ali, 500, due_in=-1)
        self.client.post(PAYMENTS, {'debt': d1.pk, 'amount': 400, 'date': str(self.today)}, format='json')
        text = self.lines()
        self.assertIn("1 ta, jami 1 100", text)
        self.assertEqual(text.count("Ali"), 1)

    def test_paid_or_dateless_debts_are_silent(self):
        paid = self.debt(self.party('Ali'), 1000, due_in=-5)
        self.pay(paid, 1000)
        self.debt(self.party('Vali'), 1000, due_in=None)
        self.assertEqual(debt_lines(self.farm, self.today), [])

    def test_included_in_daily_alerts(self):
        self.debt(self.party('Ali'), 1000, due_in=-1)
        self.assertIn("Mijozlardan to'lov kutilmoqda", "\n".join(build_alert_lines(self.farm, self.today)))
