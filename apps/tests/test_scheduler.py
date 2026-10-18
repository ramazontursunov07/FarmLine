from datetime import datetime
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.users.digest_runner import send_due_digest
from apps.users.models import DigestRun


def at(hour, minute=0, day=18):
    """Toshkent vaqti bilan 2026-10-<day> soat hour:minute."""
    return timezone.make_aware(datetime(2026, 10, day, hour, minute))


@override_settings(DIGEST_HOUR=8)
class SendDueDigestTests(TestCase):
    def test_does_nothing_before_digest_hour(self):
        with patch('apps.users.digest_runner.send_digests') as send:
            self.assertIsNone(send_due_digest(at(7, 59)))
        send.assert_not_called()
        self.assertEqual(DigestRun.objects.count(), 0)

    def test_sends_once_after_digest_hour(self):
        with patch('apps.users.digest_runner.send_digests', return_value=(2, 0)) as send:
            self.assertTrue(send_due_digest(at(8, 0)))
            self.assertIsNone(send_due_digest(at(8, 1)))  # bugun allaqachon yuborilgan
            self.assertIsNone(send_due_digest(at(21, 30)))
        self.assertEqual(send.call_count, 1)
        self.assertEqual(DigestRun.objects.get().date.isoformat(), '2026-10-18')

    def test_late_start_still_sends_today(self):
        # Server soat 8 dan keyin ishga tushsa ham (yoki qayta yuklansa), bugungi hisobot yuboriladi
        with patch('apps.users.digest_runner.send_digests', return_value=(1, 0)) as send:
            self.assertTrue(send_due_digest(at(15, 10)))
        send.assert_called_once()

    def test_next_day_sends_again(self):
        with patch('apps.users.digest_runner.send_digests', return_value=(1, 0)) as send:
            self.assertTrue(send_due_digest(at(9, 0, day=18)))
            self.assertTrue(send_due_digest(at(9, 0, day=19)))
        self.assertEqual(send.call_count, 2)

    def test_failure_allows_retry_and_returns_false(self):
        with patch('apps.users.digest_runner.send_digests', side_effect=RuntimeError('telegram')):
            self.assertFalse(send_due_digest(at(9, 0)))
        self.assertEqual(DigestRun.objects.count(), 0)  # belgi olib tashlandi: keyingi urinish qayta yuboradi
        with patch('apps.users.digest_runner.send_digests', return_value=(1, 0)) as send:
            self.assertTrue(send_due_digest(at(9, 10)))
        send.assert_called_once()
