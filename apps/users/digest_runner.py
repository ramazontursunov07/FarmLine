"""Kunlik hisobotni yuborish: buyruq ham (send_daily_digest), tashqi chaqiruv ham (cron endpoint) shu yerdan foydalanadi."""
import logging
import threading

from django.db import connections

from .digest import build_owner_digest, build_worker_digest
from .models import DigestRun, User
from .telegram import send_message

logger = logging.getLogger(__name__)


def send_digests(today, dry=False, out=None):
    """
    Telegrami ulangan foydalanuvchilarga hisobot yuboradi.
    dry=True bo'lsa, yubormasdan matnlarni out ga yozadi. (yuborilgan, yuborilmagan) qaytaradi.
    """
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
                if out is not None:
                    out.write(f"--- {user.username} ---\n{text}\n")
                sent += 1
            elif send_message(user.telegram_chat_id, text):
                sent += 1
            else:
                skipped += 1
    return sent, skipped


def _run(today, run_pk):
    try:
        sent, skipped = send_digests(today)
        logger.info("Kunlik hisobot: %s ta yuborildi, %s ta yuborilmadi", sent, skipped)
    except Exception:
        logger.exception("Kunlik hisobotni yuborib bo'lmadi")
        # Keyingi chaqiruv qayta urinib ko'rishi uchun "bugun yuborilgan" belgisi olib tashlanadi
        DigestRun.objects.filter(pk=run_pk).delete()


def _thread_main(today, run_pk):
    try:
        _run(today, run_pk)
    finally:
        connections.close_all()  # bu oqimning baza ulanishlarini yopamiz


def run_digest_in_background(today, run_pk):
    """So'rovga darhol javob qaytarish uchun yuborishni alohida oqimda bajaradi (ko'p foydalanuvchida uzoq cho'ziladi)."""
    threading.Thread(target=_thread_main, args=(today, run_pk), daemon=True).start()
