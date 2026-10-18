from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.users.digest_runner import send_digests


class Command(BaseCommand):
    help = "Telegrami ulangan fermerlarga kunlik hisobot, ishchilarga ochiq vazifalar ro'yxatini yuboradi."

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help="Yubormasdan, matnlarni ekranga chiqaradi")

    def handle(self, *args, **options):
        dry = options['dry_run']
        sent, skipped = send_digests(timezone.localdate(), dry=dry, out=self.stdout)

        self.stdout.write(self.style.SUCCESS(
            f"Tayyor: {sent} ta xabar {'ko‘rsatildi' if dry else 'yuborildi'}, {skipped} ta yuborilmadi."
        ))
