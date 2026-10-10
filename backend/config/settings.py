"""Django settings for the PakkaTrip admin + operator API."""
import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env", override=True)

SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]
DEBUG = os.environ.get("DJANGO_DEBUG", "False") == "True"
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",")

# The public site address. Moving to another domain (e.g. pakkatrip.co.in) is a change here and in
# DJANGO_ALLOWED_HOSTS, nothing else.
SITE_URL = os.environ.get("SITE_URL", "http://localhost:5173").rstrip("/")
CSRF_TRUSTED_ORIGINS = os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", SITE_URL).split(",")

# Business details shown on the Contact, Terms, Privacy and Refund pages (required for Razorpay activation and
# by the Consumer Protection (E-Commerce) Rules, 2020).
SITE_INFO = {
    "url": SITE_URL,
    "domain": SITE_URL.split("://", 1)[-1],
    "brand": os.environ.get("SITE_BRAND", "PakkaTrip"),
    "legal_name": os.environ.get("BUSINESS_LEGAL_NAME", ""),
    "address": os.environ.get("BUSINESS_ADDRESS", ""),
    "gstin": os.environ.get("BUSINESS_GSTIN", ""),
    "support_email": os.environ.get("SUPPORT_EMAIL", ""),
    "support_phone": os.environ.get("SUPPORT_PHONE", ""),
    "support_hours": os.environ.get("SUPPORT_HOURS", "Monday to Saturday, 10 am to 7 pm IST"),
    "grievance_officer": os.environ.get("GRIEVANCE_OFFICER_NAME", ""),
    "grievance_email": os.environ.get("GRIEVANCE_OFFICER_EMAIL", ""),
    "grievance_phone": os.environ.get("GRIEVANCE_OFFICER_PHONE", ""),
    "jurisdiction": os.environ.get("LEGAL_JURISDICTION_CITY", ""),
}

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "accounts",
    "core",
    "operators",
    "catalog",
    "inventory",
    "bookings",
    "payments",
    "reviews",
    "api",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
    ]},
}]
WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("DB_NAME", "pakkatrip"),
        "USER": os.environ.get("DB_USER", "pakkatrip"),
        "PASSWORD": os.environ.get("DB_PASSWORD", ""),
        "HOST": os.environ.get("DB_HOST", "127.0.0.1"),
        "PORT": os.environ.get("DB_PORT", "5432"),
    }
}

AUTH_USER_MODEL = "accounts.User"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 6}},
]

LANGUAGE_CODE = "en-in"
TIME_ZONE = "Asia/Kolkata"   # stored in UTC (USE_TZ), shown in IST
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"          # uploaded package photos
PRIVATE_MEDIA_ROOT = BASE_DIR / "private_media"   # encrypted operator ID documents; never served at a public URL

# SMS one-time codes via MSG91 (https://control.msg91.com: Authkey, plus a DLT-approved OTP template whose
# variable is the code). Without MSG91_AUTH_KEY, development (DEBUG on) shows the code on screen instead;
# with DEBUG off nothing can be sent.
MSG91_AUTH_KEY = os.environ.get("MSG91_AUTH_KEY", "")
MSG91_OTP_TEMPLATE_ID = os.environ.get("MSG91_OTP_TEMPLATE_ID", "")
OTP_TTL_MINUTES = 10
PASSWORD_RESET_TIMEOUT = 60 * 60   # seconds a "forgot password" link stays valid

# Email (one-time codes, password-reset links, booking confirmations). Gmail: EMAIL_HOST_USER is the Gmail address and EMAIL_HOST_PASSWORD a 16-character App Password
# (Google Account → Security → 2-Step Verification → App passwords). Without a login, development prints emails to the log.
EMAIL_HOST = os.environ.get("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "").replace(" ", "")   # Google shows it in groups of 4
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "True") == "True"
EMAIL_TIMEOUT = 15
EMAIL_BACKEND = ("django.core.mail.backends.smtp.EmailBackend" if EMAIL_HOST_USER
                 else "django.core.mail.backends.console.EmailBackend")
DEFAULT_FROM_EMAIL = f"{SITE_INFO['brand']} <{EMAIL_HOST_USER or 'noreply@localhost'}>"

# Razorpay (test keys start with rzp_test_). The webhook secret is the one you set on the Razorpay dashboard.
RAZORPAY_KEY_ID = os.environ.get("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET", "")
RAZORPAY_WEBHOOK_SECRET = os.environ.get("RAZORPAY_WEBHOOK_SECRET", "")

# Cashfree Payments (PG v3 API)
CASHFREE_APP_ID = os.environ.get("CASHFREE_APP_ID", "")
CASHFREE_SECRET_KEY = os.environ.get("CASHFREE_SECRET_KEY", "")
CASHFREE_WEBHOOK_SECRET = os.environ.get("CASHFREE_WEBHOOK_SECRET", "")
CASHFREE_ENV = os.environ.get("CASHFREE_ENV", "TEST").upper()
CASHFREE_API_VERSION = os.environ.get("CASHFREE_API_VERSION", "2023-08-01")

PAYMENT_HOLD_MINUTES = int(os.environ.get("PAYMENT_HOLD_MINUTES", "15"))   # seats held while the traveller pays
# RazorpayX (operator payouts): the RazorpayX account number money is paid out from (Dashboard → My Account).
RAZORPAYX_ACCOUNT_NUMBER = os.environ.get("RAZORPAYX_ACCOUNT_NUMBER", "")
RAZORPAYX_PAYOUT_MODE = os.environ.get("RAZORPAYX_PAYOUT_MODE", "IMPS")   # IMPS (instant, up to ₹5 lakh) or NEFT
# Key for encrypting operator bank account numbers and PAN at rest (Fernet key; see core/crypto.py).
FIELD_ENCRYPTION_KEY = os.environ.get("FIELD_ENCRYPTION_KEY", "")
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 50 * 1024 * 1024   # up to 8 photos × 5 MB in one form
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework_simplejwt.authentication.JWTAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "COERCE_DECIMAL_TO_STRING": False,
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
}
