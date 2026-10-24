from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.farms import payroll


class Command(BaseCommand):
    help = "Tugagan oylar uchun ishchilar ish haqini moliyaga chiqim qilib yozadi (qayta ishlatsa ham ikki marta yozmaydi)."

    def handle(self, *args, **options):
        posted = payroll.post_due(timezone.localdate())
        self.stdout.write(f"{len(posted)} ta ish haqi chiqimi yozildi.")
