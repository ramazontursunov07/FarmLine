from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.tasks import recurring


class Command(BaseCommand):
    help = "Muddati kelgan takrorlanuvchi vazifalardan oddiy vazifa yaratadi (qayta ishlatsa ham ikki marta yaratmaydi)."

    def handle(self, *args, **options):
        created = recurring.create_due(timezone.localdate())
        self.stdout.write(f"{len(created)} ta vazifa yaratildi.")
