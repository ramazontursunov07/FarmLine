import sys
import os
import asyncio

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django
from dotenv import load_dotenv

load_dotenv()

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart, CommandObject

from apps.users.models import PasswordResetToken

BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


@dp.message(CommandStart())
async def start_handler(message: types.Message, command: CommandObject):
    token_value = command.args

    if not token_value:
        await message.answer("Salom! Bu FarmLine botiga xush kelibsiz.")
        return

    try:
        reset_token = await PasswordResetToken.objects.aget(token=token_value)
    except PasswordResetToken.DoesNotExist:
        await message.answer("Noto'g'ri yoki eskirgan havola.")
        return

    if not reset_token.is_valid():
        await message.answer("Havola muddati tugagan yoki allaqachon ishlatilgan.")
        return

    user = await reset_token.user
    user.telegram_chat_id = message.chat.id
    await user.asave()

    reset_link = f"https://farmline.uz/reset-password?token={token_value}"
    await message.answer(
        f"Salom, {user.first_name or user.username}!\n"
        f"Parolingizni yangilash uchun quyidagi havolaga o'ting:\n{reset_link}"
    )


async def main():
    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())
