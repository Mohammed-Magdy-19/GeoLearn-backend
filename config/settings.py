"""
config/settings.py

Central Django settings for the Teaching Platform.
All sensitive values are read from the .env file via python-decouple.
Never hard-code secrets here.
"""

import os
from pathlib import Path
from datetime import timedelta
from decouple import config, Csv
from dotenv import load_dotenv
import dj_database_url


# ─────────────────────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────────────────────
# 1. Establish the absolute base project root path directory
BASE_DIR = Path(__file__).resolve().parent.parent

# 2. Tell Django exactly where to look for your .env file
ENV_PATH = os.path.join(BASE_DIR, '.env')
load_dotenv(ENV_PATH) 


# ─────────────────────────────────────────────────────────────
# Security
# ─────────────────────────────────────────────────────────────
SECRET_KEY = config("SECRET_KEY")
DEBUG = config("DEBUG", default=False, cast=bool)
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="localhost", cast=Csv())


# Cleanly split comma-separated URLs from your environment configuration
FRONTEND_URLS = os.environ.get("FRONTEND_URL", "http://localhost:5173")

CORS_ALLOWED_ORIGINS = [
    url.strip() for url in FRONTEND_URLS.split(",") if url.strip()
]


# ─────────────────────────────────────────────────────────────
# Application Registry
# ─────────────────────────────────────────────────────────────
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",  # Enables refresh token rotation invalidation
    "corsheaders",
]

LOCAL_APPS = [
    "apps.authentication",
    "apps.courses",
    "apps.payments",
    "apps.notifications",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS


# ─────────────────────────────────────────────────────────────
# Middleware
# ─────────────────────────────────────────────────────────────
MIDDLEWARE = [
    # CorsMiddleware must be as high as possible — before CommonMiddleware
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"





# ... your other settings ...

# Dynamic Database Router (Neon Cloud vs Local pgAdmin Fallback)
DATABASE_URL = os.environ.get("DATABASE_URL")

if DATABASE_URL:
    print("🚀 INFO: Django is connecting to NEON CLOUD DATABASE")
    DATABASES = {
        "default": dj_database_url.config(
            default=DATABASE_URL,
            conn_max_age=600,  # Keeps connections warm for faster performance
            ssl_require=True   # Neon requires SSL for cloud data transfers
        )
    }
else:
    print("💻 INFO: Django is connecting to LOCAL PGADMIN DATABASE")
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.environ.get('DB_NAME', 'geolearn_db'),
            'USER': os.environ.get('DB_USER', 'geolearn_user'),
            'PASSWORD': os.environ.get('DB_PASSWORD', 'ahmed_2005_mido_2006__2026'),
            'HOST': os.environ.get('DB_HOST', 'localhost'),
            'PORT': os.environ.get('DB_PORT', '5432'),
        }
    }


# ─────────────────────────────────────────────────────────────
# Caching — Redis (also used by Celery broker)
# ─────────────────────────────────────────────────────────────
# REDIS_URL = config("REDIS_URL", default="redis://localhost:6379/0")

# CACHES = {
#     "default": {
#         "BACKEND": "django_redis.cache.RedisCache",
#         "LOCATION": REDIS_URL,
#         "OPTIONS": {
#             "CLIENT_CLASS": "django_redis.client.DefaultClient",
#             "SOCKET_CONNECT_TIMEOUT": 5,
#             "SOCKET_TIMEOUT": 5,
#         },
#         "KEY_PREFIX": "tp",
#     }
# }

# settings.py — replace your Redis CACHES config with this
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

# ─────────────────────────────────────────────────────────────
# Custom User Model
# Replaces Django's default User with our phone-number-based model
# ─────────────────────────────────────────────────────────────
AUTH_USER_MODEL = "authentication.CustomUser"


# ─────────────────────────────────────────────────────────────
# Django REST Framework
# ─────────────────────────────────────────────────────────────
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "20/minute",
        "user": "200/minute",
    },
}


# ─────────────────────────────────────────────────────────────
# SimpleJWT Configuration
# ─────────────────────────────────────────────────────────────
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(
        minutes=config("ACCESS_TOKEN_LIFETIME_MINUTES", default=5, cast=int)
    ),
    "REFRESH_TOKEN_LIFETIME": timedelta(
        days=config("REFRESH_TOKEN_LIFETIME_DAYS", default=7, cast=int)
    ),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": SECRET_KEY,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "AUTH_HEADER_NAME": "HTTP_AUTHORIZATION",
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
    "TOKEN_TYPE_CLAIM": "token_type",
}


# ─────────────────────────────────────────────────────────────
# CORS — Cross-Origin Resource Sharing
# ─────────────────────────────────────────────────────────────
from corsheaders.defaults import default_headers

CORS_ALLOWED_ORIGINS = config(
    "CORS_ALLOWED_ORIGINS",
    default="http://localhost:5173",
    cast=Csv(),
)
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = list(default_headers) + [
    "x-playback-token",
]


# ─────────────────────────────────────────────────────────────
# Celery — Async Task Queue (broker = Redis)
# ─────────────────────────────────────────────────────────────
# CELERY_BROKER_URL = REDIS_URL
# CELERY_RESULT_BACKEND = REDIS_URL
# CELERY_ACCEPT_CONTENT = ["json"]
# CELERY_TASK_SERIALIZER = "json"
# CELERY_RESULT_SERIALIZER = "json"
# CELERY_TIMEZONE = "Africa/Cairo"


# ─────────────────────────────────────────────────────────────
# Secure Video Subsystem Configuration
# ─────────────────────────────────────────────────────────────
# Secret key for signing playback session tokens.
# Falls back to Django SECRET_KEY if not explicitly set.
# Should be at least 32 characters for security.
SECURE_VIDEO_TOKEN_SECRET = config(
    "SECURE_VIDEO_TOKEN_SECRET",
    default=SECRET_KEY,
)

# Absolute filesystem path to the encrypted video storage directory.
# In production: must be outside the web root, readable only by the Django process.
# In development: relative path under BASE_DIR is acceptable.
SECURE_VIDEO_STREAM_PATH = config(
    "SECURE_VIDEO_STREAM_PATH",
    default=str(BASE_DIR / "secure_videos"),
)

# How long a playback session token remains valid (in hours).
# After expiry, the client must request a new token from the lesson detail endpoint.
SECURE_VIDEO_TOKEN_TTL_HOURS = config(
    "SECURE_VIDEO_TOKEN_TTL_HOURS",
    default=2,
    cast=int,
)

# Maximum number of concurrent playback sessions allowed per user.
# When exceeded, the oldest active session is automatically revoked.
# This prevents account sharing and limits concurrent streams.
SECURE_VIDEO_MAX_SESSIONS = config(
    "SECURE_VIDEO_MAX_SESSIONS",
    default=5,
    cast=int,
)

# ─────────────────────────────────────────────────────────────
# Internationalisation
# ─────────────────────────────────────────────────────────────
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Africa/Cairo"
USE_I18N = True
USE_TZ = True


# ─────────────────────────────────────────────────────────────
# Static Files
# ─────────────────────────────────────────────────────────────
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ─────────────────────────────────────────────────────────────
# Production Security Overrides (Phase 4)
# Uncomment these when DEBUG = False in production
# ─────────────────────────────────────────────────────────────
# SECURE_SSL_REDIRECT = True
# SESSION_COOKIE_SECURE = True
# CSRF_COOKIE_SECURE = True
# SECURE_HSTS_SECONDS = 31536000
# SECURE_HSTS_INCLUDE_SUBDOMAINS = True