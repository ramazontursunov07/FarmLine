import os
from datetime import timedelta
from pathlib import Path
from corsheaders.defaults import default_headers
import dj_database_url
from dotenv import load_dotenv

load_dotenv(override=True)  # .env qiymatlari tizim/IDE muhit o'zgaruvchilaridan ustun bo'lsin

BASE_DIR = Path(__file__).resolve().parent.parent


def env_list(name, default=''):
    """Vergul bilan ajratilgan env qiymatini ro'yxatga aylantiradi."""
    return [item.strip() for item in os.getenv(name, default).split(',') if item.strip()]


# SECRET_KEY .env da bo'lishi shart (yo'q bo'lsa, dastur ishga tushmaydi)
SECRET_KEY = os.environ['SECRET_KEY']

DEBUG = os.getenv('DEBUG', 'False') == 'True'

ALLOWED_HOSTS = env_list('ALLOWED_HOSTS', 'localhost,127.0.0.1')
# Render hosting o'z manzilini shu o'zgaruvchida beradi: uni qo'lda yozish shart emas
if os.getenv('RENDER_EXTERNAL_HOSTNAME'):
    ALLOWED_HOSTS.append(os.environ['RENDER_EXTERNAL_HOSTNAME'])

# Telegram va frontend sozlamalari
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_BOT_USERNAME = os.getenv('TELEGRAM_BOT_USERNAME', 'FarmLineBot')
# AI sozlamalari: AI_PROVIDER = gemini (standart) yoki openai (Groq, OpenRouter kabi OpenAI-mos API)
AI_PROVIDER = os.getenv('AI_PROVIDER', 'gemini')
AI_MODEL = os.getenv('AI_MODEL')  # bo'sh bo'lsa, provayderning standart modeli olinadi
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
AI_API_KEY = os.getenv('AI_API_KEY')
AI_BASE_URL = os.getenv('AI_BASE_URL')  # masalan https://api.groq.com/openai/v1

FRONTEND_URL = (os.getenv('FRONTEND_URL') or os.getenv('RENDER_EXTERNAL_URL') or 'http://localhost:5173').rstrip('/')
# Telegram ogohlantirishlari alohida oqimda yuboriladi (testlarda False qilinadi)
TELEGRAM_ASYNC = os.getenv('TELEGRAM_ASYNC', 'True') == 'True'

# Kunlik hisobotni tashqi rejalashtiruvchi (GitHub Actions) chaqirishi uchun maxfiy kalit.
# Berilmasa, /api/users/cron/daily-digest/ manzili butunlay o'chiq turadi (404).
CRON_SECRET = os.getenv('CRON_SECRET')

# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    'rest_framework',
    'rest_framework_simplejwt',
    'drf_yasg',
    'corsheaders',

    'apps.core',
    'apps.animals',
    'apps.farms',
    'apps.finance',
    'apps.inventory',
    'apps.tasks',
    'apps.users',
    'apps.assistant',
    'apps.weather',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',  # static va ilovaning (React) tayyor fayllarini beradi
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

AUTH_USER_MODEL = 'users.User'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# Database

# DATABASE_URL berilsa (hosting, PostgreSQL) shu ishlatiladi, bo'lmasa kompyuterdagi db.sqlite3
if os.getenv('DATABASE_URL'):
    DATABASES = {'default': dj_database_url.parse(os.environ['DATABASE_URL'], conn_max_age=600)}
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# Password validation

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization

LANGUAGE_CODE = 'en-us'

# "Bugun" va muddati o'tgan vazifalar O'zbekiston vaqti bo'yicha hisoblanishi uchun
TIME_ZONE = 'Asia/Tashkent'

USE_I18N = True

USE_TZ = True

# Static va media fayllar

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage'},
}

# Tayyor frontend (npm run build natijasi): sayt, service worker, manifest va ikonkalar bir manzildan beriladi
FRONTEND_DIST = BASE_DIR / 'frontend' / 'dist'
if FRONTEND_DIST.is_dir():
    WHITENOISE_ROOT = FRONTEND_DIST
    WHITENOISE_INDEX_FILE = True
    WHITENOISE_MIMETYPES = {'.webmanifest': 'application/manifest+json'}

MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    # Brute-force hujumlardan himoya: faqat throttle_scope berilgan view'larga ta'sir qiladi
    'DEFAULT_THROTTLE_RATES': {
        'login': '10/minute',
        'register': '10/hour',
        'forgot_password': '5/hour',
        'reset_password': '10/hour',
        'telegram_link': '10/hour',
        'export': '60/hour',
        'assistant': '60/hour',
        'cron': '30/hour',
    },
}

# Qishloqda internet kunlab uzilishi mumkin: sessiya uzoq saqlanadi va har yangilanganda yana uzayadi
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=30),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=int(os.getenv('JWT_REFRESH_DAYS', '60'))),
    'ROTATE_REFRESH_TOKENS': True,
}

# Takroriy yuborishdan himoya sarlavhasi (offline navbatdan keladi); aks holda brauzer uni to'sib qo'yadi
CORS_ALLOW_HEADERS = (*default_headers, 'idempotency-key')

CORS_ALLOWED_ORIGINS = env_list(
    'CORS_ALLOWED_ORIGINS',
    'http://localhost:5173,http://127.0.0.1:5173',
)

# Hostingda (HTTPS orqasida) ishlaganda
CSRF_TRUSTED_ORIGINS = env_list('CSRF_TRUSTED_ORIGINS', FRONTEND_URL if FRONTEND_URL.startswith('https://') else '')
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')  # proxy orqali kelgan so'rov HTTPS ekanini biladi
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
