from datetime import date
from io import StringIO
from unittest.mock import patch

from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.users import digest_runner
from apps.users.models import DigestRun, User

URL = '/api/users/cron/daily-digest/'
SECRET = 'sirli-kalit-123'
RUNNER = 'apps.users.views.run_digest_in_background'
TODAY = date(2026, 10, 16)


@override_settings(CRON_SECRET=SECRET)
class DailyDigestCronTests(TestCase):
    def setUp(self):
        cache.clear()  # so'rov cheklovi hisoblagichi testlar orasida to'planib qolmasin
        self.client = APIClient()

    def post(self, secret=SECRET, query=''):
        extra = {} if secret is None else {'HTTP_X_CRON_SECRET': secret}
        return self.client.post(URL + query, **extra)

    def test_missing_or_wrong_secret_is_404(self):
        with patch(RUNNER) as run:
            self.assertEqual(self.post(None).status_code, 404)
            self.assertEqual(self.post('boshqa').status_code, 404)
        run.assert_not_called()
        self.assertEqual(DigestRun.objects.count(), 0)

    @override_settings(CRON_SECRET=None)
    def test_disabled_when_secret_is_not_configured(self):
        with patch(RUNNER) as run:
            self.assertEqual(self.post('').status_code, 404)
            self.assertEqual(self.post('None').status_code, 404)
        run.assert_not_called()

    def test_runs_once_per_day(self):
        with patch(RUNNER) as run:
            self.assertEqual(self.post().status_code, 202)
            second = self.post()
        self.assertEqual(second.status_code, 200)
        run.assert_called_once()
        self.assertEqual(DigestRun.objects.count(), 1)

    def test_force_sends_again(self):
        with patch(RUNNER) as run:
            self.post()
            self.assertEqual(self.post(query='?force=1').status_code, 202)
        self.assertEqual(run.call_count, 2)

    def test_get_is_not_allowed(self):
        self.assertEqual(self.client.get(URL, HTTP_X_CRON_SECRET=SECRET).status_code, 405)


class DigestRunnerTests(TestCase):
    def setUp(self):
        self.linked = User.objects.create_user(username='bogliq', password='Kuchli-Parol-2026', role='fermer')
        self.linked.telegram_chat_id = '111'
        self.linked.save()
        User.objects.create_user(username='ulanmagan', password='Kuchli-Parol-2026', role='fermer')

    @patch('apps.users.digest_runner.send_message', return_value=True)
    @patch('apps.users.digest_runner.build_worker_digest', return_value='')
    @patch('apps.users.digest_runner.build_owner_digest', return_value='Hisobot')
    def test_sends_only_to_users_with_telegram(self, owner, worker, send):
        self.assertEqual(digest_runner.send_digests(TODAY), (1, 0))
        send.assert_called_once_with('111', 'Hisobot')

    @patch('apps.users.digest_runner.send_message', return_value=False)
    @patch('apps.users.digest_runner.build_worker_digest', return_value='')
    @patch('apps.users.digest_runner.build_owner_digest', return_value='Hisobot')
    def test_counts_failed_deliveries(self, owner, worker, send):
        self.assertEqual(digest_runner.send_digests(TODAY), (0, 1))

    @patch('apps.users.digest_runner.send_message')
    @patch('apps.users.digest_runner.build_worker_digest', return_value='Vazifalar')
    @patch('apps.users.digest_runner.build_owner_digest', return_value='Hisobot')
    def test_dry_run_sends_nothing(self, owner, worker, send):
        out = StringIO()
        self.assertEqual(digest_runner.send_digests(TODAY, dry=True, out=out), (2, 0))
        send.assert_not_called()
        self.assertIn('Hisobot', out.getvalue())
        self.assertIn('Vazifalar', out.getvalue())

    def test_failed_background_run_can_be_retried(self):
        run = DigestRun.objects.create(date=TODAY)
        with patch('apps.users.digest_runner.send_digests', side_effect=RuntimeError('xato')):
            digest_runner._run(TODAY, run.pk)
        self.assertFalse(DigestRun.objects.exists())

    def test_successful_background_run_keeps_the_mark(self):
        run = DigestRun.objects.create(date=TODAY)
        with patch('apps.users.digest_runner.send_digests', return_value=(1, 0)):
            digest_runner._run(TODAY, run.pk)
        self.assertTrue(DigestRun.objects.filter(pk=run.pk).exists())

    @patch('apps.users.digest_runner.build_worker_digest', return_value='')
    @patch('apps.users.digest_runner.build_owner_digest', return_value='Hisobot')
    def test_management_command_dry_run(self, owner, worker):
        out = StringIO()
        call_command('send_daily_digest', '--dry-run', stdout=out)
        self.assertIn('Hisobot', out.getvalue())
        self.assertIn('Tayyor: 1 ta', out.getvalue())
