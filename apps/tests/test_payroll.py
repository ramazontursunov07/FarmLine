from datetime import date, datetime, timezone as dt_tz
from decimal import Decimal
from unittest import mock

from django.test import override_settings
from rest_framework.test import APITestCase

from apps.farms import payroll
from apps.farms.models import Farm, SalaryPayment, Worker
from apps.finance.models import Transaction
from apps.users.models import User

WORKERS = '/api/workers/'


def make_user(username, role='fermer'):
    return User.objects.create_user(username=username, password='Kuchli-Parol-2026', role=role)


class PayrollBase(APITestCase):
    def setUp(self):
        self.owner = make_user('egasi')
        self.farm = Farm.objects.create(owner=self.owner, name='Baraka', location='Qarshi', farm_type='aralash')
        self.user = make_user('ali', 'ishchi')
        self.user.first_name = 'Ali'
        self.user.save()
        self.worker = Worker.objects.create(user=self.user, farm=self.farm)
        self.client.force_authenticate(self.owner)

    def set_salary(self, amount, since, joined=date(2026, 1, 1)):
        Worker.objects.filter(pk=self.worker.pk).update(
            monthly_salary=Decimal(amount), salary_from=since,
            joined_at=datetime(joined.year, joined.month, joined.day, 12, tzinfo=dt_tz.utc))
        self.worker.refresh_from_db()


@override_settings(TELEGRAM_ASYNC=False)
class PostDueTests(PayrollBase):
    def test_full_month_posted_on_last_day_only(self):
        self.set_salary(3_000_000, date(2026, 9, 1))
        self.assertEqual(payroll.post_due(date(2026, 9, 29)), [])  # oy hali tugamagan
        posted = payroll.post_due(date(2026, 9, 30))
        self.assertEqual(len(posted), 1)
        t = Transaction.objects.get()
        self.assertEqual((t.transaction_type, t.category, t.amount), ('chiqim', 'ish_haqi', Decimal('3000000')))
        self.assertEqual((t.farm, t.date, t.recorded_by), (self.farm, date(2026, 9, 30), self.owner))
        self.assertIn('Ali', t.description)

    def test_idempotent(self):
        self.set_salary(3_000_000, date(2026, 9, 1))
        payroll.post_due(date(2026, 9, 30))
        payroll.post_due(date(2026, 9, 30))
        payroll.post_due(date(2026, 10, 5))
        self.assertEqual(Transaction.objects.count(), 1)
        self.assertEqual(SalaryPayment.objects.count(), 1)

    def test_missed_months_are_caught_up(self):
        self.set_salary(1_000_000, date(2026, 7, 1))
        posted = payroll.post_due(date(2026, 10, 2))  # server o'chiq bo'lgan: iyul, avgust, sentabr
        self.assertEqual([p.month for p in posted], [date(2026, 7, 1), date(2026, 8, 1), date(2026, 9, 1)])
        self.assertEqual(Transaction.objects.count(), 3)

    def test_no_back_pay_before_salary_was_set(self):
        self.set_salary(1_000_000, date(2026, 10, 1), joined=date(2026, 1, 1))
        self.assertEqual(payroll.post_due(date(2026, 10, 15)), [])
        self.assertEqual(Transaction.objects.count(), 0)

    def test_first_partial_month_is_prorated(self):
        self.set_salary(3_000_000, date(2026, 9, 16))  # 16..30 sentabr = 15 kun / 30
        payroll.post_due(date(2026, 9, 30))
        self.assertEqual(Transaction.objects.get().amount, Decimal('1500000'))

    def test_joined_later_than_salary_from_uses_joined_date(self):
        self.set_salary(3_100_000, date(2026, 9, 1), joined=date(2026, 10, 16))  # 16..31 okt = 16 kun / 31
        payroll.post_due(date(2026, 10, 31))
        self.assertEqual(Transaction.objects.get().amount, Decimal('1600000'))

    def test_zero_salary_is_skipped(self):
        self.set_salary(0, date(2026, 9, 1))
        self.assertEqual(payroll.post_due(date(2026, 12, 31)), [])

    def test_deleted_expense_is_not_reposted(self):
        self.set_salary(3_000_000, date(2026, 9, 1))
        payroll.post_due(date(2026, 9, 30))
        Transaction.objects.all().delete()
        payroll.post_due(date(2026, 10, 3))
        self.assertEqual(Transaction.objects.count(), 0)
        self.assertEqual(SalaryPayment.objects.count(), 1)

    def test_year_end_rollover(self):
        self.set_salary(1_000_000, date(2026, 12, 1))
        posted = payroll.post_due(date(2027, 1, 31))
        self.assertEqual([p.month for p in posted], [date(2026, 12, 1), date(2027, 1, 1)])

    def test_owner_gets_telegram_message(self):
        self.owner.telegram_chat_id = '111'
        self.owner.save()
        self.set_salary(3_000_000, date(2026, 9, 1))
        with mock.patch('apps.users.notify.send_message') as send, self.captureOnCommitCallbacks(execute=True):
            payroll.post_due(date(2026, 9, 30))
        self.assertEqual(send.call_count, 1)
        self.assertIn('3 000 000', send.call_args[0][1])

    def test_command(self):
        from django.core.management import call_command
        self.set_salary(3_000_000, date(2026, 9, 1))
        with mock.patch('apps.farms.payroll.timezone.localdate', return_value=date(2026, 9, 30)):
            call_command('post_salaries')
        self.assertEqual(Transaction.objects.count(), 1)


class WorkerSalaryApiTests(PayrollBase):
    def test_owner_sets_salary_and_start_date(self):
        r = self.client.patch(f'{WORKERS}{self.worker.pk}/', {'monthly_salary': '2500000'}, format='json')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()['monthly_salary'], '2500000.00')
        self.worker.refresh_from_db()
        from django.utils import timezone
        self.assertEqual(self.worker.salary_from, timezone.localdate())

    def test_changing_amount_keeps_start_date(self):
        self.set_salary(1_000_000, date(2026, 3, 1))
        self.client.patch(f'{WORKERS}{self.worker.pk}/', {'monthly_salary': '1500000'}, format='json')
        self.worker.refresh_from_db()
        self.assertEqual((self.worker.monthly_salary, self.worker.salary_from), (Decimal('1500000'), date(2026, 3, 1)))

    def test_negative_salary_rejected(self):
        r = self.client.patch(f'{WORKERS}{self.worker.pk}/', {'monthly_salary': '-5'}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_worker_cannot_change_own_salary(self):
        self.client.force_authenticate(self.user)
        r = self.client.patch(f'{WORKERS}{self.worker.pk}/', {'monthly_salary': '99999999'}, format='json')
        self.assertEqual(r.status_code, 403)
        self.worker.refresh_from_db()
        self.assertEqual(self.worker.monthly_salary, 0)

    def test_create_worker_with_salary(self):
        r = self.client.post(WORKERS, {'farm': self.farm.pk, 'username': 'vali', 'password': 'Kuchli-Parol-2026',
                                       'first_name': 'Vali', 'monthly_salary': '2000000'}, format='json')
        self.assertEqual(r.status_code, 201, r.content)
        w = Worker.objects.get(user__username='vali')
        self.assertEqual(w.monthly_salary, Decimal('2000000'))
        self.assertIsNotNone(w.salary_from)

    def test_last_salary_month_shown(self):
        self.set_salary(1_000_000, date(2026, 9, 1))
        payroll.post_due(date(2026, 9, 30))
        r = self.client.get(f'{WORKERS}?farm={self.farm.pk}')
        rows = r.json()['results'] if isinstance(r.json(), dict) else r.json()
        self.assertEqual(rows[0]['last_salary_month'], '2026-09')

    def test_deleting_worker_keeps_expenses(self):
        self.set_salary(1_000_000, date(2026, 9, 1))
        payroll.post_due(date(2026, 9, 30))
        self.client.delete(f'{WORKERS}{self.worker.pk}/')
        self.assertEqual(Transaction.objects.count(), 1)
