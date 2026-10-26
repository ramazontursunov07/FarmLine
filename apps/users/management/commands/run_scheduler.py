import logging
import time

from django.core.management.base import BaseCommand
from django.db import close_old_connections

from apps.farms.payroll import post_due_once_a_day
from apps.tasks.recurring import create_due_once_a_day
from apps.users.digest_runner import send_due_digest

logger = logging.getLogger(__name__)

CHECK_EVERY = 60  # soniya: vaqt kelganini shuncha vaqtda bir tekshiramiz
RETRY_AFTER_ERROR = 600  # xato bo'lsa, qayta urinishdan oldin kutish (Telegram yoki baza muammosida har daqiqa urinmaslik uchun)


class Command(BaseCommand):
    help = (
        "Ichki rejalashtiruvchi: har kuni DIGEST_HOUR (standart 8:00, Toshkent) dan keyin kunlik hisobotni, "
        "shu jumladan tug'ishi yaqin bug'oz hayvonlar eslatmasini Telegramga yuboradi. "
        "Server ishga tushganda start.sh orqali fonda ishlaydi. --once: bir marta tekshirib chiqadi."
    )

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true', help="Bir marta tekshirib chiqib ketadi")

    def handle(self, *args, **options):
        once = options['once']
        self.stdout.write("Rejalashtiruvchi ishga tushdi.")
        while True:
            delay = CHECK_EVERY
            try:
                close_old_connections()
                try:
                    post_due_once_a_day()  # oy oxirida ishchilar ish haqi chiqimi
                except Exception:
                    logger.exception("Ish haqini yozishda xato")
                try:
                    create_due_once_a_day()  # takrorlanuvchi vazifalar
                except Exception:
                    logger.exception("Takrorlanuvchi vazifalarni yaratishda xato")
                result = send_due_digest()
                if result is False:
                    delay = RETRY_AFTER_ERROR
                elif result:
                    self.stdout.write("Kunlik hisobot yuborildi.")
            except Exception:
                logger.exception("Rejalashtiruvchida xato")
                delay = RETRY_AFTER_ERROR
            if once:
                return
            time.sleep(delay)
