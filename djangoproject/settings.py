"""
Django settings for djangoproject project.
"""

import os
from pathlib import Path
from urllib.parse import urlparse

from django.core.exceptions import ImproperlyConfigured


BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    value = os.getenv(name, default)
    return [item.strip() for item in value.split(",") if item.strip()]


def env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    return int(value)


ENVIRONMENT = os.getenv("DJANGO_ENV", "development").strip().lower()
IS_PRODUCTION = ENVIRONMENT == "production"
DEBUG = env_bool("DJANGO_DEBUG", default=not IS_PRODUCTION)

default_secret_key = "dev-only-secret-key-change-me"
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", default_secret_key)
if IS_PRODUCTION and SECRET_KEY == default_secret_key:
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must be set in production.")

ALLOWED_HOSTS = env_list(
    "DJANGO_ALLOWED_HOSTS",
    "django-project-1-g31l.onrender.com,localhost,127.0.0.1",
)
if IS_PRODUCTION and not ALLOWED_HOSTS:
    raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS must be set in production.")

CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")


INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "checkins",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "djangoproject.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "djangoproject.wsgi.application"
ASGI_APPLICATION = "djangoproject.asgi.application"


def database_config() -> dict:
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        if IS_PRODUCTION:
            raise ImproperlyConfigured("DATABASE_URL must be set in production.")
        return {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }

    parsed = urlparse(database_url)
    scheme = parsed.scheme.lower()
    if scheme == "sqlite":
        db_name = parsed.path or "/db.sqlite3"
        resolved_name = db_name[1:] if db_name.startswith("/") else db_name
        return {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / resolved_name,
        }
    if scheme in {"postgres", "postgresql"}:
        return {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": parsed.path.lstrip("/"),
            "USER": parsed.username or "",
            "PASSWORD": parsed.password or "",
            "HOST": parsed.hostname or "",
            "PORT": str(parsed.port or ""),
            "CONN_MAX_AGE": int(os.getenv("DJANGO_DB_CONN_MAX_AGE", "60")),
            "CONN_HEALTH_CHECKS": True,
        }
    raise ImproperlyConfigured(f"Unsupported DATABASE_URL scheme: {scheme}")


DATABASES = {
    "default": database_config(),
}


cache_url = os.getenv("CACHE_URL", "").strip()
if IS_PRODUCTION and not cache_url:
    raise ImproperlyConfigured("CACHE_URL must be set in production.")

if cache_url:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": cache_url,
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "djangoproject-local",
        }
    }


AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


LANGUAGE_CODE = "en-us"
TIME_ZONE = os.getenv("DJANGO_TIME_ZONE", "UTC")
USE_I18N = True
USE_TZ = True


STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")
STATIC_URL = "/static/"
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}


LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "login"

SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = "DENY"

if IS_PRODUCTION:
    SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = int(os.getenv("DJANGO_SECURE_HSTS_SECONDS", "31536000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS", True)
    SECURE_HSTS_PRELOAD = env_bool("DJANGO_SECURE_HSTS_PRELOAD", True)
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
else:
    SECURE_SSL_REDIRECT = False
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False
    SECURE_HSTS_SECONDS = 0
    SECURE_HSTS_INCLUDE_SUBDOMAINS = False
    SECURE_HSTS_PRELOAD = False


SMS_BACKEND = os.getenv("SMS_BACKEND", "checkins.sms.ConsoleSMSBackend")
SMS_FROM_NUMBER = os.getenv("SMS_FROM_NUMBER", "")
SMS_TWILIO_ACCOUNT_SID = os.getenv("SMS_TWILIO_ACCOUNT_SID", "")
SMS_TWILIO_AUTH_TOKEN = os.getenv("SMS_TWILIO_AUTH_TOKEN", "")
SMS_RATE_LIMIT_SECONDS = env_int("SMS_RATE_LIMIT_SECONDS", 30)
DRIVER_CHECKIN_RATE_LIMIT_SECONDS = env_int("DRIVER_CHECKIN_RATE_LIMIT_SECONDS", 60)
SMS_MAX_ATTEMPTS = max(1, env_int("SMS_MAX_ATTEMPTS", 5))
SMS_RETRY_BASE_SECONDS = max(5, env_int("SMS_RETRY_BASE_SECONDS", 30))
SMS_WORKER_POLL_SECONDS = max(1, env_int("SMS_WORKER_POLL_SECONDS", 5))
SMS_WORKER_HEARTBEAT_TTL = max(10, env_int("SMS_WORKER_HEARTBEAT_TTL", 60))
UVICORN_FORWARDED_ALLOW_IPS = (
    os.getenv("UVICORN_FORWARDED_ALLOW_IPS", "127.0.0.1").strip() or "127.0.0.1"
)


def validate_sms_settings() -> None:
    if not IS_PRODUCTION:
        return
    if SMS_BACKEND == "checkins.sms.TwilioSMSBackend":
        missing = [
            name
            for name, value in (
                ("SMS_FROM_NUMBER", SMS_FROM_NUMBER),
                ("SMS_TWILIO_ACCOUNT_SID", SMS_TWILIO_ACCOUNT_SID),
                ("SMS_TWILIO_AUTH_TOKEN", SMS_TWILIO_AUTH_TOKEN),
            )
            if not value
        ]
        if missing:
            raise ImproperlyConfigured(
                f"Missing required Twilio production settings: {', '.join(missing)}"
            )


validate_sms_settings()


DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


LOG_LEVEL = os.getenv("DJANGO_LOG_LEVEL", "INFO").upper()
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": LOG_LEVEL,
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": LOG_LEVEL,
            "propagate": False,
        },
        "checkins": {
            "handlers": ["console"],
            "level": LOG_LEVEL,
            "propagate": False,
        },
    },
}
