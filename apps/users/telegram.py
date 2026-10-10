import json
import logging
import urllib.error
import urllib.request

from django.conf import settings

logger = logging.getLogger(__name__)

_bot_username_cache = None


def get_bot_username():
    """
    Botning haqiqiy username'ini TOKEN orqali Telegramning o'zidan oladi (getMe),
    shuning uchun havola doim token tegishli bo'lgan botga olib boradi.
    Telegramga ulanib bo'lmasa, .env dagi TELEGRAM_BOT_USERNAME ishlatiladi.
    """
    global _bot_username_cache
    if _bot_username_cache:
        return _bot_username_cache

    token = settings.TELEGRAM_BOT_TOKEN
    if token:
        try:
            with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/getMe", timeout=5) as response:
                username = json.loads(response.read().decode('utf-8')).get('result', {}).get('username')
            if username:
                _bot_username_cache = username
                return username
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            # Tokenni log'ga tushirmaslik uchun faqat xato turini yozamiz
            logger.warning("Bot username'ini olib bo'lmadi: %s", exc.__class__.__name__)

    return settings.TELEGRAM_BOT_USERNAME.lstrip('@')


def build_bot_link(code):
    """Botni ochuvchi havola: https://t.me/<bot>?start=<kod>"""
    return f"https://t.me/{get_bot_username()}?start={code}"


def send_message(chat_id, text):
    """
    Telegram Bot API orqali xabar yuboradi (qo'shimcha kutubxonasiz).
    Muvaffaqiyatli bo'lsa True, aks holda False qaytaradi va xatoni tashlamaydi.
    """
    token = settings.TELEGRAM_BOT_TOKEN
    if not token or not chat_id:
        return False

    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=json.dumps({'chat_id': chat_id, 'text': text}).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status == 200
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        logger.warning("Telegram xabar yuborilmadi: %s", exc.__class__.__name__)
        return False
