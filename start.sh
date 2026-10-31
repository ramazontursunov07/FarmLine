#!/bin/sh
set -e
python manage.py migrate --noinput
# So'rov cheklovlari uchun umumiy kesh jadvali (DATABASE_URL bo'lganda ishlatiladi; mavjud bo'lsa, tegmaydi)
if [ -n "$DATABASE_URL" ]; then
    python manage.py createcachetable || echo "createcachetable bajarilmadi"
fi
  python manage.py build_knowledge_index || echo "build_knowledge_index bajarilmadi: qidiruv oddiy rejimda ishlaydi"
# RUN_BOT=1 bo'lsa, Telegram bot ham shu serverda fon rejimida ishga tushadi
if [ "$RUN_BOT" = "1" ]; then
    python bot/main.py &
fi
# Kunlik hisobot va tug'ish eslatmasini Telegramga yuboruvchi rejalashtiruvchi (o'chirish: RUN_SCHEDULER=0)
if [ "${RUN_SCHEDULER:-1}" = "1" ]; then
    python manage.py run_scheduler &
fi
exec gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 2 --timeout 60
