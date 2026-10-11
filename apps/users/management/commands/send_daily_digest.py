from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.users.digest import build_owner_digest, build_worker_digest
from apps.users.models import User
from apps.users.telegram import send_message


class Command(BaseCommand):
    help = "Telegrami ulangan fermerlarga kunlik hisobot, ishchilarga ochiq vazifalar ro'yxatini yuboradi."

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help="Yubormasdan, matnlarni ekranga chiqaradi")

    def handle(self, *args, **options):
        today = timezone.localdate()
        dry = options['dry_run']
        sent = skipped = 0

        users = User.objects.exclude(telegram_chat_id__isnull=True).exclude(telegram_chat_id='')
        for user in users:
            messages = []
            owner_text = build_owner_digest(user, today)
            if owner_text:
                messages.append(owner_text)
            worker_text = build_worker_digest(user, today)
            if worker_text:
                messages.append(worker_text)

            for text in messages:
                if dry:
                    self.stdout.write(f"--- {user.username} ---\n{text}\n")
                    sent += 1
                elif send_message(user.telegram_chat_id, text):
                    sent += 1
                else:
                    skipped += 1

        self.stdout.write(self.style.SUCCESS(
            f"Tayyor: {sent} ta xabar {'ko‘rsatildi' if dry else 'yuborildi'}, {skipped} ta yuborilmadi."
        ))
