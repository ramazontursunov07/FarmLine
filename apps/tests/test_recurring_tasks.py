from datetime import date

from django.test import override_settings
from rest_framework.test import APITestCase

from apps.farms.models import Farm, Worker
from apps.tasks import recurring
from apps.tasks.models import RecurringTask, Task
from apps.users.models import User

URL = '/api/tasks-recurring/'


def mk(username, role='fermer'):
    return User.objects.create_user(username=username, password='Kuchli-Parol-2026', role=role)


class Base(APITestCase):
    def setUp(self):
        self.owner = mk('egasi')
        self.farm = Farm.objects.create(owner=self.owner, name='Baraka', location='Qarshi', farm_type='aralash')
        self.worker_user = mk('ali', 'ishchi')
        Worker.objects.create(user=self.worker_user, farm=self.farm)
        self.client.force_authenticate(self.owner)

    def make(self, **kw):
        data = dict(farm=self.farm, title='Vaksina', frequency='yillik', next_due=date(2026, 10, 30),
                    anchor_day=30, created_by=self.owner)
        data.update(kw)
        return RecurringTask.objects.create(**data)


@override_settings(TELEGRAM_ASYNC=False)
class CreateDueTests(Base):
    def test_not_due_yet(self):
        self.make()
        self.assertEqual(recurring.create_due(date(2026, 10, 1)), [])
        self.assertEqual(Task.objects.count(), 0)

    def test_creates_on_due_date_and_advances(self):
        rt = self.make()
        made = recurring.create_due(date(2026, 10, 30))
        self.assertEqual(len(made), 1)
        self.assertEqual(Task.objects.get().due_date, date(2026, 10, 30))
        rt.refresh_from_db()
        self.assertEqual(rt.next_due, date(2027, 10, 30))

    def test_second_run_same_day_does_nothing(self):
        self.make()
        recurring.create_due(date(2026, 10, 30))
        self.assertEqual(recurring.create_due(date(2026, 10, 30)), [])
        self.assertEqual(Task.objects.count(), 1)

    def test_lead_days(self):
        self.make(lead_days=7)
        self.assertEqual(recurring.create_due(date(2026, 10, 22)), [])
        self.assertEqual(len(recurring.create_due(date(2026, 10, 23))), 1)

    def test_missed_periods_create_single_task(self):
        rt = self.make(frequency='haftalik', next_due=date(2026, 9, 1), anchor_day=1)
        made = recurring.create_due(date(2026, 10, 25))
        self.assertEqual(len(made), 1)
        rt.refresh_from_db()
        self.assertGreaterEqual(rt.next_due, date(2026, 10, 25))
        self.assertEqual(rt.next_due.weekday(), date(2026, 9, 1).weekday())

    def test_month_end_clamp(self):
        rt = self.make(frequency='oylik', next_due=date(2027, 1, 31), anchor_day=31)
        recurring.create_due(date(2027, 1, 31))
        rt.refresh_from_db()
        self.assertEqual(rt.next_due, date(2027, 2, 28))
        recurring.create_due(date(2027, 2, 28))
        rt.refresh_from_db()
        self.assertEqual(rt.next_due, date(2027, 3, 31))

    def test_inactive_skipped(self):
        self.make(is_active=False)
        self.assertEqual(recurring.create_due(date(2026, 11, 1)), [])

    def test_assignee_kept(self):
        self.make(assigned_to=self.worker_user)
        recurring.create_due(date(2026, 10, 30))
        self.assertEqual(Task.objects.get().assigned_to, self.worker_user)


class ApiTests(Base):
    def payload(self, **kw):
        d = {'farm': self.farm.id, 'title': 'Qoramolga vaksina', 'frequency': 'yillik', 'next_due': '2026-11-15'}
        d.update(kw)
        return d

    def test_owner_creates(self):
        r = self.client.post(URL, self.payload(), format='json')
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(RecurringTask.objects.get().anchor_day, 15)

    def test_worker_cannot_see_or_create(self):
        self.client.force_authenticate(self.worker_user)
        r = self.client.post(URL, self.payload(), format='json')
        self.assertIn(r.status_code, (400, 403))
        self.make()
        self.assertEqual(len(self.client.get(URL).json()), 0)

    def test_other_owner_cannot_use_my_farm(self):
        other = mk('boshqa')
        self.client.force_authenticate(other)
        r = self.client.post(URL, self.payload(), format='json')
        self.assertEqual(r.status_code, 403)

    def test_assignee_must_be_worker_of_farm(self):
        stranger = mk('begona', 'ishchi')
        r = self.client.post(URL, self.payload(assigned_to=stranger.id), format='json')
        self.assertEqual(r.status_code, 400)
