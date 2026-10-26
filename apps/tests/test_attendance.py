from datetime import date
from decimal import Decimal

from django.test import override_settings

from apps.farms import payroll
from apps.farms.models import Attendance, SalaryPayment
from apps.finance.models import Transaction
from apps.tests.test_payroll import PayrollBase, make_user

URL = '/api/attendance/'


class MarkTests(PayrollBase):
    def mark(self, day, status='kelmadi', **kw):
        return self.client.post(URL, {'worker': self.worker.pk, 'date': day, 'status': status, **kw}, format='json')

    def test_owner_marks_and_unmarks(self):
        self.assertEqual(self.mark('2026-09-03').status_code, 200)
        self.assertEqual(self.mark('2026-09-03', 'ruxsat').status_code, 200)  # o'zgartirish
        self.assertEqual(Attendance.objects.get().status, 'ruxsat')
        self.assertEqual(self.mark('2026-09-03', 'keldi').status_code, 204)
        self.assertEqual(Attendance.objects.count(), 0)

    def test_future_day_rejected(self):
        self.assertEqual(self.mark('2999-01-01').status_code, 400)

    def test_worker_cannot_mark_but_sees_own(self):
        self.mark('2026-09-03')
        self.client.force_authenticate(self.user)
        self.assertEqual(self.mark('2026-09-04').status_code, 403)
        rows = self.client.get(f'{URL}?farm={self.farm.pk}&month=2026-09').json()
        self.assertEqual(len(rows), 1)

    def test_other_worker_sees_nothing(self):
        self.mark('2026-09-03')
        self.client.force_authenticate(make_user('boshqa', 'ishchi'))
        self.assertEqual(self.client.get(URL).json(), [])

    def test_month_filter(self):
        self.mark('2026-09-03')
        self.mark('2026-10-03')
        self.assertEqual(len(self.client.get(f'{URL}?month=2026-09').json()), 1)

    def test_locked_after_salary_posted(self):
        self.set_salary(3_000_000, date(2026, 9, 1))
        payroll.post_due(date(2026, 10, 1))
        self.assertEqual(self.mark('2026-09-10').status_code, 400)


@override_settings(TELEGRAM_ASYNC=False)
class DeductionTests(PayrollBase):
    def absent(self, *days, status='kelmadi'):
        for d in days:
            Attendance.objects.create(worker=self.worker, date=d, status=status)

    def test_deducts_absent_days(self):
        self.set_salary(3_000_000, date(2026, 9, 1))  # 30 kun: kuniga 100 000
        self.absent(date(2026, 9, 3), date(2026, 9, 4))
        payroll.post_due(date(2026, 10, 1))
        p = SalaryPayment.objects.get()
        self.assertEqual((p.absent_days, p.deduction, p.amount), (2, Decimal('200000'), Decimal('2800000')))
        t = Transaction.objects.get()
        self.assertEqual(t.amount, Decimal('2800000'))
        self.assertIn('2 kun', t.description)

    def test_excused_not_deducted(self):
        self.set_salary(3_000_000, date(2026, 9, 1))
        self.absent(date(2026, 9, 3), status='ruxsat')
        payroll.post_due(date(2026, 10, 1))
        self.assertEqual(SalaryPayment.objects.get().amount, Decimal('3000000'))

    def test_last_day_absence_counts(self):
        self.set_salary(3_000_000, date(2026, 9, 1))
        self.absent(date(2026, 9, 30))
        payroll.post_due(date(2026, 9, 30))  # hali yozilmaydi
        self.assertEqual(SalaryPayment.objects.count(), 0)
        payroll.post_due(date(2026, 10, 1))
        self.assertEqual(SalaryPayment.objects.get().amount, Decimal('2900000'))

    def test_deduction_capped_at_salary(self):
        self.set_salary(3_000_000, date(2026, 9, 16))  # 15 kun = 1 500 000
        self.absent(*[date(2026, 9, d) for d in range(16, 31)])
        self.absent(date(2026, 9, 5))  # ish boshlanmasdan oldin: hisobga olinmaydi
        payroll.post_due(date(2026, 10, 1))
        p = SalaryPayment.objects.get()
        self.assertEqual(p.absent_days, 15)
        self.assertEqual(p.amount, Decimal('0'))
