#!/bin/sh
set -e
python manage.py migrate --noinput
# RUN_BOT=1 bo'lsa, Telegram bot ham shu serverda fon rejimida ishga tushadi
if [ "$RUN_BOT" = "1" ]; then
    python bot/main.py &
fi
exec gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 2 --timeout 60
