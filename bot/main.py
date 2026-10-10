import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django
from dotenv import load_dotenv

load_dotenv(override=True)  # .env qiymatlari tizim/IDE muhit o'zgaruvchilaridan ustun bo'lsin

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart, CommandObject

from apps.users.models import TelegramLinkToken, User

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
        f"Endi parolni tiklash havolalari shu yerga keladi."
    )


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
    asyncio.run(main())
