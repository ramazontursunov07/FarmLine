import asyncio
import io
import logging
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django
from dotenv import load_dotenv

load_dotenv(override=True)  # .env qiymatlari tizim/IDE muhit o'zgaruvchilaridan ustun bo'lsin

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, CommandStart, CommandObject
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from apps.assistant import bot_service
from apps.users.models import TelegramLinkToken, User

logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
if not BOT_TOKEN:
    raise SystemExit("TELEGRAM_BOT_TOKEN .env faylida topilmadi")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


@dp.message(CommandStart())
async def start_handler(message: types.Message, command: CommandObject):
    code = command.args

    if not code:
        await message.answer(
            "Salom! Bu FarmLine boti.\n"
            "Telegramni akkauntingizga ulash uchun saytda Profil bo'limidan "
            "\"Telegramni ulash\" tugmasini bosing."
        )
        return

    # Faqat shaxsiy chat ulanadi (guruh yoki kanal emas)
    if message.chat.type != 'private':
        await message.answer("Telegramni faqat shaxsiy chatda ulash mumkin.")
        return

    try:
        link_token = await TelegramLinkToken.objects.select_related('user').aget(code=code)
    except TelegramLinkToken.DoesNotExist:
        await message.answer("Noto'g'ri yoki eskirgan havola.")
        return

    if not link_token.is_valid():
        await message.answer("Havola muddati tugagan yoki allaqachon ishlatilgan.")
        return

    chat_id = str(message.chat.id)
    user = link_token.user

    # Bitta Telegram bitta akkauntga ulanadi
    taken = await User.objects.filter(telegram_chat_id=chat_id).exclude(pk=user.pk).aexists()
    if taken:
        await message.answer("Bu Telegram boshqa akkauntga ulangan.")
        return

    # Kod bir martalik: atomik tarzda "ishlatilgan" deb belgilanadi
    updated = await TelegramLinkToken.objects.filter(pk=link_token.pk, is_used=False).aupdate(is_used=True)
    if not updated:
        await message.answer("Havola allaqachon ishlatilgan.")
        return

    user.telegram_chat_id = chat_id
    await user.asave(update_fields=['telegram_chat_id'])

    await message.answer(
        f"Tayyor, {user.first_name or user.username}! Telegram akkauntingizga ulandi.\n"
        f"Endi parolni tiklash havolalari va kunlik hisobot shu yerga keladi.\n\n"
        f"Saytga kirmasdan ham yozishingiz mumkin: matn yoki ovozli xabar yuboring.\n{HELP_EXAMPLES}"
    )


# ---------------------------------------------------------------- matn va ovoz bilan yozish

MAX_VOICE_SECONDS = 60
MAX_VOICE_BYTES = 5 * 1024 * 1024

HELP_EXAMPLES = (
    "Masalan:\n"
    "• «14-sigir 12 litr, 15-sigir 9 litr sut berdi»\n"
    "• «5 qop yem ishlatdim»\n"
    "• «ombordan 50 kg omuxta yem chiqar»\n"
    "• «300 kg yem keldi, 2 million so'm»\n"
    "• «bugun 200 000 so'm kommunal chiqim yoz»\n"
    "Ovozli xabar ham yuborishingiz mumkin. Hech narsa o'zi yozilmaydi: avval nima yozilishini ko'rsataman, "
    "«Tasdiqlash» tugmasini bossangiz yoziladi."
)
NOT_LINKED = (
    "Bu Telegram hali akkauntga ulanmagan. Saytda Profil bo'limidan \"Telegramni ulash\" tugmasini bosing."
)


def confirm_keyboard(pending_id):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"ok:{pending_id}"),
        InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"no:{pending_id}"),
    ]])


async def process_text(message: types.Message, user, text: str):
    """Matnni AI ga beradi; taklif bo'lsa tasdiqlash tugmalari bilan, bo'lmasa oddiy javob."""
    await bot.send_chat_action(message.chat.id, 'typing')
    reply, pending_id = await asyncio.to_thread(bot_service.ask, user, text)
    if pending_id:
        await message.answer(reply, reply_markup=confirm_keyboard(pending_id))
    else:
        await message.answer(reply)


@dp.message(Command('help'), F.chat.type == 'private')
async def help_handler(message: types.Message):
    await message.answer("FarmLine bot.\n\n" + HELP_EXAMPLES)


@dp.message(Command('yangi'), F.chat.type == 'private')
async def reset_handler(message: types.Message):
    user = await asyncio.to_thread(bot_service.get_user, message.chat.id)
    if user:
        bot_service.reset_history(user.pk)
    await message.answer("Yangi suhbat boshlandi.")


@dp.message(F.text, ~F.text.startswith('/'), F.chat.type == 'private')
async def text_handler(message: types.Message):
    user = await asyncio.to_thread(bot_service.get_user, message.chat.id)
    if user is None:
        await message.answer(NOT_LINKED)
        return
    await process_text(message, user, message.text)


@dp.message(F.voice | F.audio, F.chat.type == 'private')
async def voice_handler(message: types.Message):
    user = await asyncio.to_thread(bot_service.get_user, message.chat.id)
    if user is None:
        await message.answer(NOT_LINKED)
        return

    media = message.voice or message.audio
    if (media.duration or 0) > MAX_VOICE_SECONDS:
        await message.answer(f"Ovozli xabar juda uzun. {MAX_VOICE_SECONDS} soniyagacha yuboring.")
        return
    if (media.file_size or 0) > MAX_VOICE_BYTES:
        await message.answer("Ovoz fayli juda katta.")
        return

    await bot.send_chat_action(message.chat.id, 'typing')
    buffer = io.BytesIO()
    try:
        await bot.download(media, destination=buffer)
    except Exception:
        logger.exception("Ovozni yuklab olib bo'lmadi")
        await message.answer("Ovozni yuklab olib bo'lmadi. Qayta yuboring yoki matn bilan yozing.")
        return

    mime = getattr(media, 'mime_type', None) or 'audio/ogg'
    text = await asyncio.to_thread(bot_service.voice_to_text, buffer.getvalue(), mime)
    if not text:
        await message.answer("Ovozni tushuna olmadim. Aniqroq gapirib qayta yuboring yoki matn bilan yozing.")
        return

    # Eshitilgan matn ko'rsatiladi: noto'g'ri tushunilgan bo'lsa, foydalanuvchi darrov ko'radi
    await message.answer(f"🎤 «{text}»")
    await process_text(message, user, text)


@dp.callback_query(F.data.regexp(r'^(ok|no):\d+$'))
async def decision_handler(callback: types.CallbackQuery):
    message = callback.message
    if message is None or message.chat.type != 'private':
        await callback.answer()
        return
    user = await asyncio.to_thread(bot_service.get_user, message.chat.id)
    if user is None:
        await callback.answer(NOT_LINKED, show_alert=True)
        return

    decision, pending_id = callback.data.split(':')
    if decision == 'ok':
        done, result = await asyncio.to_thread(bot_service.confirm_action, user, int(pending_id))
        outcome = result if done else f"❌ {result}"
    else:
        outcome = await asyncio.to_thread(bot_service.cancel_action, user, int(pending_id))

    # Tugmalar olib tashlanadi: ikkinchi marta bosib bo'lmaydi
    try:
        await message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await bot.send_message(message.chat.id, outcome)
    await callback.answer()


async def main():
    me = await bot.get_me()
    print(f"Bot ishga tushdi: @{me.username}")

    # .env dagi username botning haqiqiy username'iga mos bo'lishi shart, aks holda
    # sayt foydalanuvchini boshqa botga yo'naltiradi
    configured = os.getenv('TELEGRAM_BOT_USERNAME', '').lstrip('@')
    if configured.lower() != (me.username or '').lower():
        print(
            f"DIQQAT: .env dagi TELEGRAM_BOT_USERNAME={configured!r}, "
            f"lekin bu token @{me.username} botiga tegishli. "
            f"TELEGRAM_BOT_USERNAME={me.username} deb o'zgartiring va Django serverni qayta ishga tushiring."
        )

    await dp.start_polling(bot)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
    asyncio.run(main())
