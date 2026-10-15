"""
Telegram orqali ogohlantirishlar.

- Xabar so'rov (request) ichida emas, alohida oqimda yuboriladi, shuning uchun
  Telegram sekin javob bersa ham API sekinlashmaydi.
- Xabar faqat tranzaksiya muvaffaqiyatli tugagandan (commit) keyin yuboriladi,
  shuning uchun bekor bo'lgan amal haqida xabar ketib qolmaydi.
- Telegram ulanmagan foydalanuvchilar jimgina o'tkazib yuboriladi.
"""
import threading

from django.conf import settings
from django.db import transaction

from .telegram import send_message


def display_name(user):
    return (user.get_full_name() or user.username) if user else "Noma'lum"


def notify_users(users, text):
    """Telegrami ulangan foydalanuvchilarga xabar yuboradi (takrorlanuvchilar bir marta)."""
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