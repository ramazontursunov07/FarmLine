from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.animals.models import Animal, AnimalGroup, AnimalType
from apps.farms.models import Farm, Worker
from apps.notifications import services
from apps.notifications.models import Notification
from apps.users.models import User
from apps.users.notify import notify_users

URL = '/api/notifications/'


class NotificationBase(TestCase):
    def setUp(self):
        cache.clear()
        self.owner = User.objects.create_user(username='egasi', password='Kuchli-Parol-2026', role='fermer')
        self.other = User.objects.create_user(username='boshqa', password='Kuchli-Parol-2026', role='fermer')
        self.farm = Farm.objects.create(owner=self.owner, name='Baraka', location='Qarshi', farm_type='aralash')
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def make(self, user=None, **extra):
        data = dict(user=user or self.owner, title='Sarlavha')
        data.update(extra)
        return Notification.objects.create(**data)

    def cow_due_in(self, days, tag='14'):
        group = AnimalGroup.objects.filter(farm=self.farm).first() or AnimalGroup.objects.create(
            farm=self.farm, animal_type=AnimalType.objects.create(name='Sigir'), count=5)
        today = timezone.localdate()
        return Animal.objects.create(
            farm=self.farm, group=group, tag_number=tag, name='Oqbosh',
            pregnant_since=today - timedelta(days=283 - days), due_date=today + timedelta(days=days))


class NotifyUsersTests(NotificationBase):
    def test_creates_in_app_notification_without_telegram(self):
        with patch('apps.users.notify.send_message') as send:
            notify_users([self.owner, self.owner, None], "💸 Katta chiqim\nUstoz: 500 000 so'm")
        send.assert_not_called()  # Telegram ulanmagan
        n = Notification.objects.get()
        self.assertEqual(n.user, self.owner)
        self.assertEqual(n.title, "💸 Katta chiqim")
        self.assertEqual(n.body, "Ustoz: 500 000 so'm")
        self.assertEqual(n.kind, 'event')

    def test_in_app_failure_does_not_break_telegram(self):
        self.owner.telegram_chat_id = '123'
        self.owner.save()
        with patch('apps.notifications.services.from_text', side_effect=RuntimeError('x')), \
                patch('apps.users.notify.send_message') as send, self.captureOnCommitCallbacks(execute=True), \
                self.settings(TELEGRAM_ASYNC=False):
            notify_users([self.owner], 'Salom')
        send.assert_called_once()


class ServiceTests(NotificationBase):
    def test_dedupe_key_prevents_duplicates(self):
        services.create([self.owner], 'calving', 'A', dedupe_key='k1')
        services.create([self.owner], 'calving', 'A', dedupe_key='k1')
        services.create([self.other], 'calving', 'A', dedupe_key='k1')
        self.assertEqual(Notification.objects.filter(user=self.owner).count(), 1)
        self.assertEqual(Notification.objects.filter(user=self.other).count(), 1)

    def test_empty_dedupe_key_allows_repeats(self):
        services.create([self.owner], 'event', 'A')
        services.create([self.owner], 'event', 'A')
        self.assertEqual(Notification.objects.count(), 2)

    def test_sync_alerts_writes_calving_once_per_day(self):
        self.cow_due_in(5)
        self.assertGreaterEqual(services.sync_alerts(self.owner), 1)
        n = Notification.objects.get(kind='calving')
        self.assertIn("Tug'ishi yaqin", n.title)
        self.assertIn('Oqbosh', n.body)
        self.assertEqual(n.link, f'/farms/{self.farm.pk}/animals')
        cache.clear()
        self.assertEqual(services.sync_alerts(self.owner), 0)  # shu kun uchun allaqachon yozilgan
        self.assertEqual(Notification.objects.filter(kind='calving').count(), 1)

    def test_sync_is_throttled_by_cache(self):
        services.sync_alerts(self.owner)
        self.cow_due_in(5)
        self.assertEqual(services.sync_alerts(self.owner), 0)  # cooldown ichida qayta hisoblanmaydi

    def test_worker_gets_only_calving_and_dry_off(self):
        worker = User.objects.create_user(username='ishchi', password='Kuchli-Parol-2026', role='ishchi')
        Worker.objects.create(user=worker, farm=self.farm)
        self.cow_due_in(5)
        services.sync_alerts(worker)
        kinds = set(Notification.objects.filter(user=worker).values_list('kind', flat=True))
        self.assertEqual(kinds, {'calving', 'dry_off'})  # boshqa turdagi eslatmalar ishchiga yozilmaydi

    def test_old_notifications_cleaned_up(self):
        old_read = self.make(is_read=True)
        old_unread = self.make()
        fresh = self.make()
        Notification.objects.filter(pk=old_read.pk).update(created_at=timezone.now() - timedelta(days=31))
        Notification.objects.filter(pk=old_unread.pk).update(created_at=timezone.now() - timedelta(days=31))
        Notification.objects.filter(pk=fresh.pk).update(created_at=timezone.now() - timedelta(days=1))
        services.cleanup(self.owner)
        self.assertEqual(set(Notification.objects.values_list('pk', flat=True)), {old_unread.pk, fresh.pk})
        Notification.objects.filter(pk=old_unread.pk).update(created_at=timezone.now() - timedelta(days=91))
        services.cleanup(self.owner)
        self.assertEqual(list(Notification.objects.values_list('pk', flat=True)), [fresh.pk])

    def test_farm_name_in_title_with_several_farms(self):
        Farm.objects.create(owner=self.owner, name='Ikkinchi', location='X', farm_type='aralash')
        self.cow_due_in(5)
        services.sync_alerts(self.owner)
        self.assertIn('— Baraka', Notification.objects.get(kind='calving').title)


class ApiTests(NotificationBase):
    def test_requires_auth(self):
        self.assertEqual(APIClient().get(URL).status_code, 401)
        self.assertEqual(APIClient().get(URL + 'count/').status_code, 401)

    def test_list_only_own_with_unread_count(self):
        self.make(title='Mening')
        self.make(title='Mening 2', is_read=True)
        self.make(user=self.other, title='Boshqaniki')
        data = self.client.get(URL).json()
        self.assertEqual(data['unread_count'], 1)
        self.assertEqual({r['title'] for r in data['results']}, {'Mening', 'Mening 2'})
        self.assertEqual(self.client.get(URL + 'count/').json(), {'unread_count': 1})

    def test_unread_filter(self):
        self.make(title='Yangi')
        self.make(title='Eski', is_read=True)
        rows = self.client.get(URL, {'unread': '1'}).json()['results']
        self.assertEqual([r['title'] for r in rows], ['Yangi'])

    def test_list_includes_fresh_alerts(self):
        self.cow_due_in(2)
        data = self.client.get(URL).json()
        self.assertTrue(any(r['kind'] == 'calving' for r in data['results']))
        self.assertGreaterEqual(data['unread_count'], 1)

    def test_list_survives_alert_failure(self):
        self.make()
        with patch('apps.notifications.services.sync_alerts', side_effect=RuntimeError('x')):
            r = self.client.get(URL)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['unread_count'], 1)

    def test_mark_read_by_ids_ignores_foreign(self):
        a, b = self.make(), self.make()
        foreign = self.make(user=self.other)
        r = self.client.post(URL + 'read/', {'ids': [a.pk, foreign.pk]}, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['unread_count'], 1)
        a.refresh_from_db();
        b.refresh_from_db();
        foreign.refresh_from_db()
        self.assertTrue(a.is_read)
        self.assertFalse(b.is_read)
        self.assertFalse(foreign.is_read)

    def test_mark_all_read(self):
        self.make();
        self.make()
        other = self.make(user=self.other)
        r = self.client.post(URL + 'read/', {'all': True}, format='json')
        self.assertEqual(r.json()['unread_count'], 0)
        other.refresh_from_db()
        self.assertFalse(other.is_read)

    def test_mark_read_validates_input(self):
        for body in ({}, {'ids': 'x'}, {'ids': ['a']}, {'ids': [True]}, {'all': 'yes'}):
            self.assertEqual(self.client.post(URL + 'read/', body, format='json').status_code, 400, body)

    def test_clear_deletes_only_own_read(self):
        self.make(is_read=True)
        keep = self.make()
        foreign = self.make(user=self.other, is_read=True)
        r = self.client.post(URL + 'clear/')
        self.assertEqual(r.json()['unread_count'], 1)
        self.assertEqual(set(Notification.objects.values_list('pk', flat=True)), {keep.pk, foreign.pk})
