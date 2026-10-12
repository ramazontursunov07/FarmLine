import os
from datetime import timedelta
from pathlib import Path
from corsheaders.defaults import default_headers
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

# Telegram va frontend sozlamalari
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_BOT_USERNAME = os.getenv('TELEGRAM_BOT_USERNAME', 'FarmLineBot')
FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://localhost:5173').rstrip('/')
# Telegram ogohlantirishlari alohida oqimda yuboriladi (testlarda False qilinadi)
TELEGRAM_ASYNC = os.getenv('TELEGRAM_ASYNC', 'True') == 'True'

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
    'apps.users'
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
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
