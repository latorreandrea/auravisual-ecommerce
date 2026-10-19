import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get(
    "SECRET_KEY",
    "django-insecure-local-dev-key-change-me",
)
# Local development is the default: DEBUG is ON unless the environment explicitly
# opts out with DEVELOPMENT=0 (false/no/off are accepted too). Always set
# DEVELOPMENT=0 in production, where DEBUG would expose tracebacks and settings
# and where static/media files must be served by collectstatic plus a real static
# server (WhiteNoise/nginx) instead of `runserver`.
DEVELOPMENT = os.environ.get("DEVELOPMENT", "1").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}
DEBUG = DEVELOPMENT
ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "127.0.0.1,localhost").split(",")


INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    # Local apps come first on purpose: when two apps expose the same template
    # path, the one listed first wins. This is what lets
    # `accounts/templates/account/*` shadow the default django-allauth pages.
    "home",
    "products",
    "accounts",
    "customization",
    "cart",
    "orders",
    # Third-party apps: keep them below the local ones so template overrides work.
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "auravisual_ecommerce.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        # Project-wide templates only: `base.html` and the shared partials that
        # belong to no single app. Everything app-specific lives inside its app
        # as `<app>/templates/<app>/...`, which APP_DIRS discovers automatically.
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "cart.context.cart_context",
                "auravisual_ecommerce.context.asset_version",
            ],
        },
    },
]

WSGI_APPLICATION = "auravisual_ecommerce.wsgi.application"


DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
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

TIME_ZONE = "UTC"

USE_I18N = True

USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# ---------------------------------------------------------------------------
# Product mockups and customer customizations
# ---------------------------------------------------------------------------
# Admin mockups are optimised on upload with Pillow: resized, converted to
# WebP and stripped of metadata. Background removal is intentionally not done
# server-side: the admin uploads a transparent PNG when one is needed.
PRODUCT_MOCKUP_MAX_DIMENSION = int(os.environ.get("PRODUCT_MOCKUP_MAX_DIMENSION", "2400"))
PRODUCT_MOCKUP_WEBP_QUALITY = int(os.environ.get("PRODUCT_MOCKUP_WEBP_QUALITY", "90"))
PRODUCT_MOCKUP_MAX_UPLOAD_MB = int(os.environ.get("PRODUCT_MOCKUP_MAX_UPLOAD_MB", "20"))
PRODUCT_MOCKUP_MAX_PIXELS = int(os.environ.get("PRODUCT_MOCKUP_MAX_PIXELS", "40000000"))

# Customer uploads: the per-image cap is a hard limit, while each
# CustomizationZone can only lower it.
CUSTOMIZATION_MAX_UPLOAD_MB = int(os.environ.get("CUSTOMIZATION_MAX_UPLOAD_MB", "10"))
CUSTOMIZATION_MAX_TOTAL_UPLOAD_MB = int(os.environ.get("CUSTOMIZATION_MAX_TOTAL_UPLOAD_MB", "50"))
CUSTOMIZATION_MAX_IMAGE_PIXELS = int(os.environ.get("CUSTOMIZATION_MAX_IMAGE_PIXELS", "40000000"))
CUSTOMIZATION_PREVIEW_MAX_BYTES = int(
    os.environ.get("CUSTOMIZATION_PREVIEW_MAX_BYTES", str(100 * 1024))
)
CUSTOMIZATION_PREVIEW_WEBP_QUALITY = int(
    os.environ.get("CUSTOMIZATION_PREVIEW_WEBP_QUALITY", "80")
)
CUSTOMIZATION_PRINT_DPI = int(os.environ.get("CUSTOMIZATION_PRINT_DPI", "300"))
CUSTOMIZATION_PRINT_ASYNC = os.environ.get("CUSTOMIZATION_PRINT_ASYNC", "1").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}
# Shared secret used by the external checkout/cart app when notifying that an
# order has been paid. Keep it empty to disable the webhook.
CUSTOMIZATION_PRINT_WEBHOOK_SECRET = os.environ.get("CUSTOMIZATION_PRINT_WEBHOOK_SECRET", "")

# Cache-busting version appended to static assets from the templates
# (see auravisual_ecommerce/context.py and {% static %}?v={{ ASSET_VERSION }}).
ASSET_VERSION = os.environ.get("ASSET_VERSION", "1")

SITE_ID = 1
LOGIN_URL = "account_login"
LOGIN_REDIRECT_URL = "home:index"
LOGOUT_REDIRECT_URL = "home:index"
ACCOUNT_EMAIL_VERIFICATION = "none"
ACCOUNT_LOGIN_METHODS = {"username", "email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "username*", "password1*", "password2*"]

if DEVELOPMENT:
    # Same flag as DEBUG, so the two can never disagree (DEBUG=True with SMTP
    # would make local signup/password emails fail).
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
    DEFAULT_FROM_EMAIL = "auravisual@example.com"
else:
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_USE_TLS = True
    EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
    EMAIL_HOST = os.environ.get("EMAIL_HOST", "")
    EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
    EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASS", "")
    DEFAULT_FROM_EMAIL = os.environ.get("EMAIL_HOST_USER", "auravisual@example.com")

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
