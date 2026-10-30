from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.animals.models import AnimalEvent, MilkRecord
from apps.farms.models import Attendance, Worker
from apps.inventory.models import InventoryItem, InventoryTransaction
from apps.tasks.models import Task
from apps.tests.test_animals import AnimalCardBase, make_user
from apps.users import work_report
from apps.users.models import WorkReportRun

SEND = 'apps.users.work_report.send_message'


class WorkReportTests(AnimalCardBase):
    def setUp(self):
        super().setUp()
        self.owner.telegram_chat_id = '111'
        self.owner.save()
        self.worker.first_name = 'Ali'
        self.worker.save()
        self.animal = self.make_animal()

    def test_empty_day(self):
        text = work_report.build_work_report(self.owner, self.today)
        self.assertIn('hech narsa yozmadi', text)

    def test_no_workers_no_report(self):
        Worker.objects.all().delete()
        self.assertIsNone(work_report.build_work_report(self.owner, self.today))

    def test_lists_what_worker_did(self):
        MilkRecord.objects.create(animal=self.animal, date=self.today, liters=Decimal('12.5'), recorded_by=self.worker)
        Task.objects.create(farm=self.farm, title='Tozalash', status='bajarildi', completed_by=self.worker,
                            completed_at=timezone.now())
        AnimalEvent.objects.create(animal_group=self.group, event_type='vaksinatsiya', title='Oqma',
                                   start_date=self.today, recorded_by=self.worker)
        item = InventoryItem.objects.create(farm=self.farm, item_name='Pichan', quantity=10, unit='kg')
        InventoryTransaction.objects.create(inventory_item=item, transaction_type='sarf', quantity=2,
                                            date=self.today, recorded_by=self.worker)
        w = Worker.objects.get(user=self.worker)
        other = make_user('ishchi2', 'ishchi')
        w2 = Worker.objects.create(user=other, farm=self.farm)
        Attendance.objects.create(worker=w2, date=self.today, status='kelmadi')
        text = work_report.build_work_report(self.owner, self.today)
        self.assertIn('Ali', text)
        self.assertIn('12.5 l', text)
        self.assertIn('Tozalash', text)
        self.assertIn('Oqma', text)
        self.assertIn('Pichan', text)
        self.assertIn('Kelmadi: ishchi2', text)
        self.assertNotIn('hech narsa', text)

    def test_owner_own_records_not_listed(self):
        MilkRecord.objects.create(animal=self.animal, date=self.today, liters=5, recorded_by=self.owner)
        text = work_report.build_work_report(self.owner, self.today)
        self.assertIn('hech narsa yozmadi', text)

    def test_runs_once_after_report_hour(self):
        tz = timezone.get_current_timezone()
        early = timezone.make_aware(datetime(2026, 10, 20, 10, 0), tz)
        late = timezone.make_aware(datetime(2026, 10, 20, 21, 0), tz)
        with override_settings(REPORT_HOUR=20), patch(SEND, return_value=True) as send:
            self.assertIsNone(work_report.send_due_work_report(early))
            self.assertTrue(work_report.send_due_work_report(late))
            self.assertIsNone(work_report.send_due_work_report(late))
        send.assert_called_once()
        self.assertEqual(WorkReportRun.objects.count(), 1)


@override_settings(CRON_SECRET='kalit')
class WorkReportCronTests(AnimalCardBase):
    URL = '/api/users/cron/work-report/'

    def setUp(self):
        super().setUp()
        cache.clear()
        self.owner.telegram_chat_id = '111'
        self.owner.save()
        self.client = APIClient()

    def test_secret_required(self):
        self.assertEqual(self.client.post(self.URL).status_code, 404)

    def test_sends_once_per_day(self):
        with patch(SEND, return_value=True) as send:
            r1 = self.client.post(self.URL, HTTP_X_CRON_SECRET='kalit')
            r2 = self.client.post(self.URL, HTTP_X_CRON_SECRET='kalit')
            r3 = self.client.post(self.URL + '?force=1', HTTP_X_CRON_SECRET='kalit')
        self.assertEqual(r1.json(), {'sent': 1, 'skipped': 0})
        self.assertIn('allaqachon', r2.json()['detail'])
        self.assertEqual(r3.status_code, 200)
        self.assertEqual(send.call_count, 2)
