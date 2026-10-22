"""Telegram botning "miyasi": matn yoki ovozdan ombor/kirim-chiqim/sut yozish.

Bot (bot/main.py) faqat Telegram bilan gaplashadi. Hamma mantiq shu yerda va saytdagi AI yordamchi bilan BIR XIL:
  * AI taklif yozadi (apps.assistant.views.chat), server uni qayta tekshiradi (apps.assistant.actions);
  * foydalanuvchi "Tasdiqlash" tugmasini bosgandagina yoziladi (apps.assistant.actions.confirm);
  * yozish oddiy API'dagi perform_create() orqali ketadi: ruxsat, zaxira tekshiruvi va Telegram xabarlari bir xil.
Shu sababli bot saytdagi qoidalardan ortiq hech narsa qila olmaydi.

Funksiyalar oddiy (sinxron): bot ularni asyncio.to_thread() bilan chaqiradi.
"""
import functools
import logging
import time
from collections import defaultdict, deque

from django.conf import settings
from django.db import connections, transaction
from rest_framework.exceptions import APIException

from apps.users.models import User

from . import actions, speech
from . import views as web  # chat() ni shu modul orqali chaqiramiz (saytdagi bilan bir xil joy)
from .context import build_context
from .models import PendingAction
from .rag import build_knowledge_prompt
from .services import AIError

logger = logging.getLogger(__name__)

MAX_TEXT_LEN = 1000
HISTORY_TTL = 15 * 60  # suhbat shuncha soniyadan keyin unutiladi
HISTORY_LEN = 6  # eslab qolinadigan oxirgi xabarlar soni
RATE_WINDOW = 3600

GENERIC_ERROR = "AI hozir javob bera olmadi. Birozdan keyin qayta urinib ko'ring."
LIMIT_ERROR = "AI limiti tugadi. Birozdan keyin qayta urinib ko'ring."
RATE_ERROR = "Juda ko'p so'rov yubordingiz. Birozdan keyin qayta urinib ko'ring."

_history = {}  # user_id -> (oxirgi faollik vaqti, [xabarlar])
_calls = defaultdict(deque)  # user_id -> AI so'rovlari vaqtlari


def _close_stale_connections():
    for conn in connections.all():
        if not conn.in_atomic_block:  # tranzaksiya ichida (masalan testda) ulanishga tegilmaydi
            conn.close_if_unusable_or_obsolete()


def db_safe(fn):
    """Alohida oqimda (asyncio.to_thread) ishlaydigan funksiya uchun: ishdan keyin DB ulanishini yopadi."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        _close_stale_connections()
        try:
            return fn(*args, **kwargs)
        finally:
            _close_stale_connections()

    return wrapper


class BotRequest:
    """perform_create() faqat foydalanuvchini va (ixtiyoriy) so'rov maydonlarini o'qiydi; HTTP so'rov kerak emas."""

    def __init__(self, user):
        self.user = user
        self.data = {}
        self.query_params = {}
        self.method = 'POST'
        self.headers = {}


@db_safe
def get_user(chat_id):
    """Telegram chat_id bo'yicha ulangan akkaunt (yo'q bo'lsa None). Admin bot orqali yoza olmaydi."""
    user = User.objects.filter(telegram_chat_id=str(chat_id), is_active=True).first()
    if user is None or user.role == 'admin' or user.is_superuser:
        return None
    return user


# ---------------------------------------------------------------- suhbat xotirasi va limit

def reset_history(user_id):
    _history.pop(user_id, None)


def _get_history(user_id):
    entry = _history.get(user_id)
    if entry is None or time.time() - entry[0] > HISTORY_TTL:
        _history.pop(user_id, None)
        return []
    return list(entry[1])


def _remember(user_id, messages):
    _history[user_id] = (time.time(), messages[-HISTORY_LEN:])


def _rate_ok(user_id):
    limit = getattr(settings, 'BOT_AI_PER_HOUR', 40)
    now = time.time()
    calls = _calls[user_id]
    while calls and now - calls[0] > RATE_WINDOW:
        calls.popleft()
    if len(calls) >= limit:
        return False
    calls.append(now)
    return True


# ---------------------------------------------------------------- xabarni qayta ishlash

def format_proposal(result):
    """AI javobidan (answer_with_action natijasi) Telegram matni va (bo'lsa) taklif raqamini tuzadi."""
    action = result.get('action')
    if not action:
        return result['answer'], None
    head = web.ASK_CONFIRM
    notes = result['answer'][len(head):] if result['answer'].startswith(head) else ''
    blocks = []
    for item in action['items']:
        blocks.append(item['title'] + "\n" + "\n".join(item['details']))
    text = head + "\n\n" + "\n\n".join(blocks) + notes
    return text, action['id']


@db_safe
def ask(user, text):
    """
    Foydalanuvchi matnini AI ga beradi. (javob matni, taklif raqami yoki None) qaytaradi.
    Taklif raqami bo'lsa, bot "Tasdiqlash / Bekor qilish" tugmalarini ko'rsatadi.
    """
    text = (text or '').strip()
    if not text:
        return "Xabar bo'sh.", None
    if len(text) > MAX_TEXT_LEN:
        return f"Xabar juda uzun ({MAX_TEXT_LEN} belgigacha yozing).", None
    if not _rate_ok(user.pk):
        return RATE_ERROR, None

    messages = web.clean_history(_get_history(user.pk))
    messages.append({'role': 'user', 'content': text})

    user_texts = [m['content'] for m in messages if m['role'] == 'user'][-2:]
    extra = actions.build_action_prompt(user)
    knowledge = build_knowledge_prompt(user_texts)
    if knowledge:
        extra = f"{extra}\n\n{knowledge}" if extra else knowledge

    try:
        answer = web.chat(list(messages), build_context(user), extra_system=extra)
    except AIError as exc:
        logger.warning("Bot AI xatosi: %s: %s", exc.__class__.__name__, exc)
        return (LIMIT_ERROR if getattr(exc, 'code', None) == 429 else GENERIC_ERROR), None
    except Exception:
        logger.exception("Bot AI so'rovida kutilmagan xato")
        return GENERIC_ERROR, None

    result = web.answer_with_action(user, answer)
    reply, pending_id = format_proposal(result)
    messages.append({'role': 'assistant', 'content': result['answer']})
    _remember(user.pk, messages)
    return reply, pending_id


@db_safe
def voice_to_text(audio, mime_type='audio/ogg'):
    """Ovoz -> matn. Tanib bo'lmasa None qaytaradi (sabab logda)."""
    try:
        return speech.transcribe(audio, mime_type)
    except AIError as exc:
        logger.warning("Ovozni tanib bo'lmadi: %s", exc)
    except Exception:
        logger.exception("Ovozni matnga aylantirishda kutilmagan xato")
    return None


# ---------------------------------------------------------------- tasdiqlash / bekor qilish

def error_text(exc):
    """DRF xatosidan (ichma-ich bo'lishi mumkin) oddiy matn."""

    def flatten(detail):
        if isinstance(detail, dict):
            for value in detail.values():
                yield from flatten(value)
        elif isinstance(detail, (list, tuple)):
            for value in detail:
                yield from flatten(value)
        else:
            yield str(detail)

    return "; ".join(dict.fromkeys(flatten(exc.detail)))  # takrorlarsiz, tartib saqlanadi


@db_safe
def confirm_action(user, pending_id):
    """Taklifni bajaradi. (muvaffaqiyatli, foydalanuvchiga matn). Taklif faqat egasiniki bo'lishi mumkin."""
    try:
        with transaction.atomic():
            # Qulf: tugma ikki marta bosilsa ham amal bir marta bajariladi
            pending = PendingAction.objects.select_for_update().filter(pk=pending_id, user=user).first()
            if pending is None:
                return False, "Amal topilmadi."
            code, body = actions.confirm(BotRequest(user), pending)
    except APIException as exc:
        return False, "Bajarib bo'lmadi: " + error_text(exc)
    except Exception:
        logger.exception("Bot orqali tasdiqlashda kutilmagan xato")
        return False, "Bajarib bo'lmadi. Birozdan keyin qayta urinib ko'ring."
    if code == 200:
        reset_history(user.pk)  # bajarilgan amalning gapi keyingi savolga aralashmasin
        return True, "\n".join(body['results'])
    return False, body['detail']


@db_safe
def cancel_action(user, pending_id):
    from django.utils import timezone
    updated = PendingAction.objects.filter(pk=pending_id, user=user, status='kutilmoqda').update(
        status='bekor', resolved_at=timezone.now())
    reset_history(user.pk)
    return "Bekor qilindi. Hech narsa yozilmadi." if updated else "Bu amal allaqachon hal qilingan."
