from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.core.models import IdempotencyRecord


class Command(BaseCommand):
    help = "Eski Idempotency-Key yozuvlarini o'chiradi (bazada to'planib qolmasligi uchun, cron'da ishlating)."

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=30, help="Shuncha kundan eski yozuvlar o'chiriladi")

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(days=options['days'])
        deleted, _ = IdempotencyRecord.objects.filter(created_at__lt=cutoff).delete()
        self.stdout.write(self.style.SUCCESS(f"{deleted} ta eski yozuv o'chirildi."))
