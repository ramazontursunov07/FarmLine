"""
Telegram orqali ogohlantirishlar.

- Xabar so'rov (request) ichida emas, alohida oqimda yuboriladi, shuning uchun
  Telegram sekin javob bersa ham API sekinlashmaydi.
- Xabar faqat tranzaksiya muvaffaqiyatli tugagandan (commit) keyin yuboriladi,
  shuning uchun bekor bo'lgan amal haqida xabar ketib qolmaydi.
- Telegram ulanmagan foydalanuvchilar jimgina o'tkazib yuboriladi.
"""
import logging
import threading

from django.conf import settings
from django.db import transaction

from .telegram import send_message

logger = logging.getLogger(__name__)


def display_name(user):
    return (user.get_full_name() or user.username) if user else "Noma'lum"


def notify_users(users, text, link=''):
    """
    Foydalanuvchilarga xabar: sayt ichidagi bildirishnoma (hamma uchun) va Telegram (ulanganlar uchun).
    Takrorlanuvchilar bir marta olinadi.
    """
    try:
        from apps.notifications.services import from_text
        with transaction.atomic():  # xato bo'lsa, tashqi tranzaksiya buzilmasin
            from_text([u for u in users if u is not None], text, link=link)
    except Exception:
        logger.exception("Sayt ichidagi bildirishnomani yozib bo'lmadi")
    chat_ids = {u.telegram_chat_id for u in users if u is not None and u.telegram_chat_id}
    if not chat_ids:
        return

    def run():
        for chat_id in chat_ids:
            send_message(chat_id, text)

    def dispatch():
        if getattr(settings, 'TELEGRAM_ASYNC', True):
            threading.Thread(target=run, daemon=True).start()
        else:
            run()

    transaction.on_commit(dispatch)


"""O'rganildi."""
